import os

import docker
import dotenv
import nano
import nanolib
from retry import retry

import common

RPC_PORT = 17076
BURN_ACCOUNT = "nano_1111111111111111111111111111111111111111111111111111hifc8npp"
DEFAULT_REPR = "nano_000000000000000000000000000000000000000000000000000000000000"


class Block:
    def __init__(self, block_nlib: nanolib.Block, prev_block):
        self.block_nlib = block_nlib
        self.prev_block = prev_block

    @property
    def balance(self):
        return self.block_nlib.balance

    @property
    def account(self):
        return self.block_nlib.account

    @property
    def representative(self):
        return self.block_nlib.representative

    @property
    def block_hash(self):
        return self.block_nlib.block_hash

    @property
    def send_amount(self):
        diff = self.prev_block.balance - self.balance
        if diff <= 0:
            raise ValueError("Not a send block")
        return diff


class Chain:
    __unpublished = []

    def __init__(self, account_id, private_key, frontier):
        self.account_id = account_id
        self.private_key = private_key
        self.frontier = frontier

    @staticmethod
    def random_account():
        seed = nanolib.generate_seed()
        account_id = nanolib.generate_account_id(seed, 0)
        private_key = nanolib.generate_account_private_key(seed, 0)
        return Chain(account_id, private_key, None)

    def send(self, account, amount):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if not self.frontier:
            raise ValueError("Account not opened")

        account_id = account.account_id
        block_nlib = Block(
            block_type="state",
            account=self.account_id,
            representative=self.frontier.representative,
            previous=self.frontier.block_hash,
            link_as_account=account_id,
            balance=self.frontier.balance - amount,
        )

        block = Block(block_nlib, self.frontier)
        self.frontier = block
        self.__unpublished.append(block)
        return block

    def receive(self, block: Block, representative=None):
        if not self.frontier:
            # open account

            if not representative:
                representative_id = DEFAULT_REPR
            else:
                representative_id = representative.account_id

            block_nlib = Block(
                block_type="state",
                account=self.account_id,
                representative=representative_id,
                previous=self.frontier.block_hash,
                link_as_account=self.account_id,
                balance=block.send_amount,
            )
            block = Block(block_nlib, None)

        else:
            if not representative:
                representative_id = self.frontier.representative
            else:
                representative = representative.account_id

            block_nlib = Block(
                block_type="state",
                account=self.account_id,
                representative=representative_id,
                previous=self.frontier.block_hash,
                link_as_account=self.account_id,
                balance=int(self.frontier.balance + block.send_amount),
            )
            block = Block(block_nlib, self.frontier)

        self.frontier = block
        self.__unpublished.append(block)
        return block


class NanoWalletAccount:
    def __init__(self, wallet, account_id, private_key):
        self.node = wallet.node
        self.wallet = wallet
        self.account_id = account_id
        self.private_key = private_key

    def print_info(self):
        print("account:", self.account_id)
        print("balance:", self.balance)
        print("pending:", self.pending)
        print()

    @property
    def balance(self):
        res = self.node.rpc.account_balance(self.account_id)
        return res["balance"]

    @property
    def pending(self):
        res = self.node.rpc.account_balance(self.account_id)
        return res["pending"]

    def send(self, account, amount):
        if isinstance(account, NanoWalletAccount):
            destination_id = account.account_id
        else:
            destination_id = account

        res = self.node.rpc.send(
            wallet=self.wallet.wallet_id,
            source=self.account_id,
            destination=destination_id,
            amount=amount,
        )

    def to_chain(self):
        frontier_hash = self.node.rpc.account_info(self.account_id)["frontier"]
        frontier_dict = self.node.rpc.block(frontier_hash)
        frontier_nlib = nanolib.Block.from_dict(frontier_dict, verify=False)
        frontier = Block(frontier_nlib, None)
        return Chain(self.account_id, self.private_key, frontier)


class NanoWallet:
    def __init__(self, node, wallet_id):
        self.node = node
        self.wallet_id = wallet_id

    def create_account(self, private_key=None):
        if not private_key:
            seed = nanolib.generate_seed()
            private_key = nanolib.generate_account_private_key(seed, 0)

        account_id = self.node.rpc.wallet_add(wallet=self.wallet_id, key=private_key)
        return NanoWalletAccount(self, account_id, private_key)


class NanoNode:
    def __init__(self, container):
        self.container = container
        self.rpc = nano.rpc.Client(f"http://localhost:{self.host_rpc_port}")

    @retry(tries=15, delay=0.3)
    def ensure_started(self):
        self.rpc.version()

    def print_info(self):
        print("name:", self.container.name)
        print("port:", self.host_rpc_port)
        block_count = self.rpc.block_count()
        print("blocks count    :", block_count["count"])
        print("blocks cemented :", block_count["cemented"])
        print("blocks unchecked:", block_count["unchecked"])
        print("version:", self.rpc.version())
        print()

    @property
    def host_rpc_port(self):
        return int(self.container.ports[f"{RPC_PORT}/tcp"][0]["HostPort"])

    @property
    def name(self):
        return self.container.name

    def create_wallet(self, private_key=None):
        wallet_id = self.rpc.wallet_create()
        wallet = NanoWallet(self, wallet_id)
        account = wallet.create_account(private_key=private_key)
        return wallet, account


class NanoTest:
    name_prefix = "nano-baseline"

    nodes = []
    __node_containers = []

    def setup(self):
        self.network_name = f"{self.name_prefix}_network"

        self.client = docker.from_env()
        self.node_env = dotenv.dotenv_values("node.env")

        self.__cleanup_docker()

        self.__setup_network()
        self.__setup_genesis()
        self.__setup_burn()

    def __setup_burn(self):
        burn_amount = int(self.node_env["NANO_TEST_BURN_AMOUNT_RAW"])
        self.genesis_account.send(BURN_ACCOUNT, burn_amount)

    def __setup_genesis(self):
        node, wallet, account = self.create_node_with_account(
            private_key=self.node_env["NANO_TEST_GENESIS_PRIV"]
        )
        self.genesis_node = node
        self.genesis_wallet = wallet
        self.genesis_account = account

    def __setup_network(self):
        if self.client.networks.list(names=[self.network_name]):
            self.network = self.client.networks.get(self.network_name)
        else:
            self.network = self.client.networks.create(
                self.network_name, check_duplicate=True
            )

    def __cleanup_docker(self):
        for cont in self.client.containers.list():
            if cont.name.startswith(self.name_prefix):
                cont.remove(force=True)

    def create_node(self):
        node = self.__create_node_container()
        node.ensure_started()
        node.print_info()

        self.nodes.append(node)
        return node

    def create_node_with_account(self, private_key=None):
        node = self.create_node()
        wallet, account = node.create_wallet(private_key=private_key)
        return node, wallet, account

    def __create_node_container(self, image_name="nano-node", default_peer=None):
        node_cli_options = "--network=test --data_path /root/Nano/"
        node_command = f"nano_node daemon ${node_cli_options} -l"
        node_main_command = (
            f"nano_node daemon {node_cli_options} --config node.peering_port=17075 -l"
        )

        if default_peer:
            peer_name = default_peer.container.name
            env = {
                "NANO_DEFAULT_PEER": peer_name,
                "NANO_TEST_PEER_NETWORK": peer_name,
                **self.node_env,
            }
        else:
            env = {
                "NANO_DEFAULT_PEER": "0",
                "NANO_TEST_PEER_NETWORK": "0",
                **self.node_env,
            }

        container = self.client.containers.run(
            image_name,
            node_main_command,
            detach=True,
            environment=env,
            name=f"{self.name_prefix}_node_{len(self.__node_containers)}",
            network=self.network_name,
            remove=True,
            ports={RPC_PORT: None},
            volumes=[
                f"{os.path.abspath('./node-config/config-node.toml')}:/root/Nano/config-node.toml",
                f"{os.path.abspath('./node-config/config-rpc.toml')}:/root/Nano/config-rpc.toml",
            ],
        )

        # for line in container.logs(stream=True):
        #     print(line.strip())

        container.reload()  # required to get auto-assigned ports
        # print(container.ports)

        self.__node_containers.append(container)

        node = NanoNode(container)
        return node

    @property
    def genesis(self):
        return self.genesis_node, self.genesis_account

    def ensure_all_confirmed(self):
        for node in self.nodes:
            node.print_info()


def create():
    nano_test = NanoTest()
    nano_test.setup()

    return nano_test


if __name__ == "__main__":
    create()

import os

import docker
import dotenv
import nano
from retry import retry

import common

RPC_PORT = 17076


class NanoWalletAccount:
    def __init__(self, wallet, account_id):
        self.node = wallet.node
        self.wallet = wallet
        self.account_id = account_id

    def print_info(self):
        print()
        print("account:", self.account_id)
        print("balance:", self.balance)

    @property
    def balance(self):
        res = self.node.rpc.account_balance(self.account_id)
        return (res["balance"], res["pending"])


class NanoWallet:
    def __init__(self, node, wallet_id):
        self.node = node
        self.wallet_id = wallet_id

    def create_account(self, private_key=None):
        if not private_key:
            account_id = self.node.rpc.account_create(wallet=self.wallet_id)
        else:
            account_id = self.node.rpc.wallet_add(wallet=self.wallet_id, key=private_key)
        return NanoWalletAccount(self, account_id)


class NanoNode:
    def __init__(self, container):
        self.container = container
        self.rpc = nano.rpc.Client(f"http://localhost:{self.host_rpc_port}")

    @retry(tries=5, delay=1)
    def ensure_started(self):
        self.rpc.version()

    def print_info(self):
        print()
        print("name:", self.container.name)
        print("port:", self.host_rpc_port)
        print("block count:", self.rpc.block_count())
        print("version:", self.rpc.version())

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

    __node_containers = []

    def setup(self):
        self.network_name = f"{self.name_prefix}_network"

        self.client = docker.from_env()
        self.node_env = dotenv.dotenv_values("node.env")

        self.__cleanup_docker()

        self.__setup_network()
        self.__setup_genesis()

        node_1 = self.__create_node(default_peer=self.genesis_node)

        pass

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

    def create_node(self):
        return self.__create_node()

    def create_node_with_account(self, private_key=None):
        node = self.create_node()
        wallet, account = node.create_wallet(private_key=private_key)
        return node, wallet, account

    def __create_node(self, image_name="nano-node", default_peer=None):
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
        print(container.ports)

        self.__node_containers.append(container)

        node = NanoNode(container)
        node.ensure_started()
        node.print_info()

        return node

    def __cleanup_docker(self):
        for cont in self.client.containers.list():
            if cont.name.startswith(self.name_prefix):
                cont.remove(force=True)


def create():
    nano_test = NanoTest()
    nano_test.setup()

    return nano_test


if __name__ == "__main__":
    create()

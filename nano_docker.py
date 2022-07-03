import os
from collections import namedtuple
from dataclasses import dataclass
from decimal import *
from typing import NamedTuple, Tuple, Union

import docker
import dotenv
import nano
import nanolib
from retry import retry

import common

RPC_PORT = 17076
HOST_RPC_PORT = 17076
BURN_ACCOUNT = "nano_1111111111111111111111111111111111111111111111111111hifc8npp"
DEFAULT_REPR = BURN_ACCOUNT
DIFFICULTY = "0000000000000000"


def account_id_from_account(account):
    if hasattr(account, "account_id"):
        account_id = account.account_id
    else:
        account_id = account
    return account_id


class Block:
    def __init__(self, block_nlib: nanolib.Block, prev_block: "Block"):
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

    def json(self):
        return self.block_nlib.json()


class BlockQueue:
    def __init__(self):
        self.__queue = []

    def append(self, block: Block):
        self.__queue.append(block)
        return block

    def pop_all(self):
        t = self.__queue
        self.__queue = []
        return t


default_queue = BlockQueue()


class Chain:
    def __init__(self, account_id, private_key, frontier):
        self.account_id = account_id
        self.private_key = private_key
        self.frontier = frontier

    @property
    def balance(self):
        return self.frontier.balance

    def send(
        self,
        account: Union["NanoWalletAccount", "Chain", str],
        amount,
        block_queue: BlockQueue = default_queue,
        fork=False,
    ):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if not self.frontier:
            raise ValueError("Account not opened")

        destination_id = account_id_from_account(account)

        block_nlib = nanolib.Block(
            block_type="state",
            account=self.account_id,
            representative=self.frontier.representative,
            previous=self.frontier.block_hash,
            link_as_account=destination_id,
            balance=self.frontier.balance - amount,
        )
        block_nlib.sign(self.private_key)
        block_nlib.solve_work(DIFFICULTY)

        block = Block(block_nlib, self.frontier)
        block_queue.append(block)
        if not fork:
            self.frontier = block
        return block

    def receive(
        self,
        block: Block,
        representative=None,
        block_queue: BlockQueue = default_queue,
        fork=False,
    ) -> Block:
        if not self.frontier:
            # open account

            if not representative:
                representative_id = DEFAULT_REPR
            else:
                representative_id = representative.account_id

            block_nlib = nanolib.Block(
                block_type="state",
                account=self.account_id,
                representative=representative_id,
                previous=None,
                link=block.block_hash,
                balance=block.send_amount,
            )
            block_nlib.sign(self.private_key)
            block_nlib.solve_work(DIFFICULTY)

            block = Block(block_nlib, None)

        else:
            if not representative:
                representative_id = self.frontier.representative
            else:
                representative = representative.account_id

            block_nlib = nanolib.Block(
                block_type="state",
                account=self.account_id,
                representative=representative_id,
                previous=self.frontier.block_hash,
                link=block.block_hash,
                balance=int(self.frontier.balance + block.send_amount),
            )
            block_nlib.sign(self.private_key)
            block_nlib.solve_work(DIFFICULTY)

            block = Block(block_nlib, self.frontier)

        block_queue.append(block)
        if not fork:
            self.frontier = block
        return block


class NanoWalletAccount:
    def __init__(self, wallet: "NanoWallet", account_id, private_key):
        self.node = wallet.node
        self.wallet = wallet
        self.account_id = account_id
        self.private_key = private_key

    def __str__(self):
        return f"[{self.account_id} | balance: {self.balance} | pending: {self.pending}]"

    @property
    def balance(self):
        res = self.node.rpc.account_balance(self.account_id)
        return Decimal(res["balance"])

    @property
    def pending(self):
        res = self.node.rpc.account_balance(self.account_id)
        return Decimal(res["pending"])

    def send(self, account: Union["NanoWalletAccount", Chain, str], amount) -> Block:
        destination_id = account_id_from_account(account)

        block_hash = self.node.rpc.send(
            wallet=self.wallet.wallet_id,
            source=self.account_id,
            destination=destination_id,
            amount=amount,
        )

        block = self.node.block(block_hash)
        return block

    def to_chain(self) -> Chain:
        frontier_hash = self.node.rpc.account_info(self.account_id)["frontier"]
        frontier = self.node.block(frontier_hash)
        return Chain(self.account_id, self.private_key, frontier)


class NanoWallet:
    def __init__(self, node: "NanoNode", wallet_id):
        self.node = node
        self.wallet_id = wallet_id

    def create_account(self, private_key=None) -> NanoWalletAccount:
        if not private_key:
            seed = nanolib.generate_seed()
            private_key = nanolib.generate_account_private_key(seed, 0)

        account_id = self.node.rpc.wallet_add(wallet=self.wallet_id, key=private_key)
        return NanoWalletAccount(self, account_id, private_key)

    def set_represenetative(self, account):
        representative_id = account_id_from_account(account)
        self.node.rpc.wallet_representative_set(
            wallet=self.wallet_id, representative=representative_id
        )


BlockCount = namedtuple("BlockCount", ["checked", "unchecked", "cemented"])


class NanoNode:
    def __init__(self, container):
        self.container = container
        self.rpc = nano.rpc.Client(f"http://localhost:{self.host_rpc_port}")

    @retry(tries=15, delay=0.3)
    def ensure_started(self):
        self.rpc.version()

    def __str__(self):
        count = self.block_count
        return f"[{self.name: <32} | port: {self.host_rpc_port: <5} | peers: {len(self.peers): >4} | checked: {count.checked: >9} | cemented: {count.cemented: >9} | unchecked: {count.unchecked: >9}]"

    @property
    def host_rpc_port(self):
        return int(self.container.ports[f"{RPC_PORT}/tcp"][0]["HostPort"])

    @property
    def name(self):
        return self.container.name

    @property
    def block_count(self) -> BlockCount:
        block_count = self.rpc.block_count()
        checked = int(block_count["count"])
        unchecked = int(block_count["unchecked"])
        cemented = int(block_count["cemented"])
        return BlockCount(checked, unchecked, cemented)

    @property
    def peers(self):
        return self.rpc.peers()

    def create_wallet(self, private_key=None, use_as_repr=False):
        wallet_id = self.rpc.wallet_create()
        wallet = NanoWallet(self, wallet_id)
        account = wallet.create_account(private_key=private_key)
        if use_as_repr:
            wallet.set_represenetative(account)
        return wallet, account

    def publish_block(self, block: Block, async_process=True):
        if async_process:
            payload = {"block": block.json(), "async": async_process}
            res = self.rpc.call("process", payload)
            return res
        else:
            return self.rpc.process(block.json())

    def pubish_queue(self, block_queue: BlockQueue, async_process=True):
        unpub = default_queue.pop_all()
        cnt = len(unpub)
        hashes = [
            self.publish_block(block, async_process=async_process) for block in unpub
        ]
        return cnt, hashes

    def block(self, hash: str, load_previous=True) -> Block:
        block_nlib = self.__nlib_block(hash)

        if load_previous and block_nlib.previous:
            prev_block = self.block(block_nlib.previous, load_previous=False)
            block = Block(block_nlib, prev_block)
        else:
            block = Block(block_nlib, None)

        return block

    def __nlib_block(self, hash):
        block_dict = self.rpc.block(hash)
        block_nlib = nanolib.Block.from_dict(block_dict, verify=False)
        return block_nlib

    def populate_backlog(self):
        res = self.rpc.call("populate_backlog")
        return True


class NodeWalletAccountTuple(NamedTuple):
    node: NanoNode
    wallet: NanoWallet
    account: NanoWalletAccount


class NanoNet:
    name_prefix = "nano-baseline"

    def __init__(self):
        self.nodes: list[NanoNode] = []
        self.__node_containers = []

    def setup(self):
        self.network_name = f"{self.name_prefix}_network"

        self.client = docker.from_env()
        self.node_env = dotenv.dotenv_values("node.env")

        self.__cleanup_docker()

        self.__setup_network()
        self.__setup_genesis()
        # self.__setup_burn()

    def __setup_burn(self):
        burn_amount = int(self.node_env["NANO_TEST_BURN_AMOUNT_RAW"])
        self.genesis.account.send(BURN_ACCOUNT, burn_amount)

    def __setup_genesis(self):
        node = self.create_node(
            do_not_peer=True, host_port=HOST_RPC_PORT, name="genesis"
        )
        wallet, account = node.create_wallet(
            private_key=self.node_env["NANO_TEST_GENESIS_PRIV"],
        )
        self.__genesis = NodeWalletAccountTuple(node, wallet, account)

    @property
    def genesis(self) -> NodeWalletAccountTuple:
        return self.__genesis

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

    def create_node(
        self, image_name="nano-node", do_not_peer=False, host_port=None, name=None
    ) -> NanoNode:
        additional_cli = os.getenv("NANO_CLI", "")
        node_cli_options = "--network=test --data_path /root/Nano/"
        node_main_command = f"nano_node daemon {node_cli_options} --config node.peering_port=17075 {additional_cli} -l"

        if not do_not_peer:
            peer_name = self.genesis.node.container.name
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

        if not name:
            name = f"{self.name_prefix}_node_{len(self.__node_containers)}"
        else:
            name = f"{self.name_prefix}_node_{name}"

        container = self.client.containers.run(
            image_name,
            node_main_command,
            detach=True,
            environment=env,
            name=name,
            network=self.network_name,
            remove=True,
            ports={RPC_PORT: host_port},
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
        self.nodes.append(node)

        node.ensure_started()

        print("Started:", node)

        return node

    def print_all_nodes(self):
        print("======================================= ALL NODES")

        for node in self.nodes:
            print(node)

        print("=======================================")


default_nanonet: NanoNet = None


def generate_random_account() -> Chain:
    seed = nanolib.generate_seed()
    account_id = nanolib.generate_account_id(seed, 0)
    private_key = nanolib.generate_account_private_key(seed, 0)
    return Chain(account_id, private_key, None)


def flush_block_queue(node: NanoNode, block_queue=default_queue, async_process=True):
    cnt, hashes = node.pubish_queue(block_queue, async_process)
    return cnt, hashes


@retry(delay=2)
def ensure_all_confirmed(nodes=None):
    if nodes is None:
        nodes = default_nanonet.nodes

    print("======================================= ENSURE ALL CONFIRMED")
    for node in nodes:
        print(node)

    target = max([node.block_count.cemented for node in nodes])
    for node in nodes:
        node.populate_backlog()

        block_count = node.block_count
        if block_count.unchecked != 0:
            raise ValueError("checked not synced")
        if block_count.checked != block_count.cemented:
            raise ValueError("not all cemented")
        if block_count.cemented != target:
            raise ValueError("not everything propagated")

    print("======================================= DONE")

def initialize():
    nanonet = NanoNet()
    nanonet.setup()

    global default_nanonet
    default_nanonet = nanonet

    return nanonet


if __name__ == "__main__":
    initialize()

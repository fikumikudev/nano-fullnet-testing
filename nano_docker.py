import os

import docker
import nano
from retry import retry

import common

RPC_PORT = 17076


class NanoNode:
    def __init__(self, container):
        self.container = container
        self.rpc = nano.rpc.Client(f"http://localhost:{self.host_rpc_port}")
        pass

    @retry(tries=5, delay=1)
    def ensure_started(self):
        self.rpc.version()

    def print_info(self):
        print("name:", self.container.name)
        print("port:", self.host_rpc_port)
        print("block count:", self.rpc.block_count())
        print("version:", self.rpc.version())
        pass

    @property
    def host_rpc_port(self):
        return int(self.container.ports[f"{RPC_PORT}/tcp"][0]["HostPort"])

    pass


class NanoNet:
    name_prefix = "nano-baseline"

    __node_containers = []

    def setup(self):
        self.network_name = f"{self.name_prefix}_network"

        self.client = docker.from_env()
        self.node_env = common.load_env_data_as_dict("node.env")

        self.__cleanup_docker()

        self.__setup_network()

        self.main_node = self.__create_node()

        node_1 = self.__create_node(default_peer=self.main_node)

        pass

    def __create_node(self, image_name="nano-node", default_peer=None):
        node_cli_options = "--network=test --data_path /root/Nano/"
        # node_cli_options = "--network=test"
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
            env = self.node_env

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


def main():
    nano_test = NanoNet()
    nano_test.setup()

    pass


if __name__ == "__main__":
    main()

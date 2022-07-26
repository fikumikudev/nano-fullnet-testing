from .common import *
from . import docker
from . import *


@title_bar(name="INITIALIZE REPRESENTATIVES")
def distribute_voting_weight_uniform(node, genesis, count, reserved):
    reps = [node.create_wallet(use_as_repr=True) for n in range(count)]

    print("Genesis:", genesis.account)

    balance_left = genesis.account.balance - reserved
    assert balance_left <= genesis.account.balance

    balance_per_rep = int(balance_left // count)
    assert balance_per_rep * count <= genesis.account.balance

    print("Balance per rep:", balance_per_rep, "x", count)

    for rep_wallet, rep_account in reps:
        print("Seeding:", rep_account, "with:", balance_per_rep)

        hsh = genesis.account.send(rep_account, balance_per_rep)

    return reps


@title_bar(name="SETUP VOTING WEIGHT UNIFORM")
def setup_voting_weight_uniform(count, reserved_raw):
    nanonet = initialize()

    setup_node = nanonet.create_node(name="setup", do_not_peer=True, track=False)

    pass

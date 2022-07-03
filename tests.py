import time
import unittest
from cmath import nan
from collections import deque
from decimal import *
from itertools import chain

from joblib import Parallel, delayed

import common
import nano_docker as nanotest
from nano_docker import BlockQueue, NanoNode, NanoNodeRPC
from common import title_bar


@title_bar(name="INITIALIZE REPRESENTATIVES")
def distribute_voting_weight_uniform(nanonet, count, reserved):
    reps = [
        nanonet.create_node(name=f"rep_{n}").create_wallet(use_as_repr=True)
        for n in range(count)
    ]

    print("Genesis:", nanonet.genesis.account)

    balance_left = nanonet.genesis.account.balance - reserved
    assert balance_left <= nanonet.genesis.account.balance

    balance_per_rep = int(balance_left // count)
    assert balance_per_rep * count <= nanonet.genesis.account.balance

    print("Balance per rep:", balance_per_rep, "x", count)

    for rep_wallet, rep_account in reps:
        print("Seeding:", rep_account, "with:", balance_per_rep)

        nanonet.genesis.account.send(rep_account, balance_per_rep)

        nanonet.ensure_all_confirmed(populate_backlog=True)

    return reps


def __spam_bin_tree_impl(rpc_address, chain_root, count):
    node = NanoNodeRPC(rpc_address)
    q = deque([chain_root])

    for i in range(count):
        r = q.popleft()
        a = nanotest.generate_random_account()
        b = nanotest.generate_random_account()

        half_balance = int(r.balance / 2)
        a.receive(r.send(a, half_balance))
        b.receive(r.send(b, half_balance))

        q.append(a)
        q.append(b)

        if i % 100 == 0:
            print("Progress:", i)

    nanotest.flush_block_queue(node)


@title_bar(name="SPAM BIN TREE")
def spam_bin_tree(node: NanoNode, spam_raw, source_account, spam_count):
    print("Spam source:", source_account)

    spam_roots = [nanotest.generate_random_account() for _ in range(spam_count)]
    for spam_root in spam_roots:
        spam_root.receive(source_account.send(spam_root, spam_raw))

    nanotest.flush_block_queue(node)

    Parallel(n_jobs=spam_count)(
        delayed(__spam_bin_tree_impl)(
            rpc_address=node.rpc_address,
            chain_root=spam_root,
            count=500,
        )
        for spam_root in spam_roots
    )


class TestStringMethods(unittest.TestCase):
    def test_nano(self):
        nanonet = nanotest.initialize()

        node = nanonet.create_node()

        spam_count = 16
        spam_raw = 2**20
        reserved_raw = spam_raw * spam_count
        reps = distribute_voting_weight_uniform(nanonet, 5, reserved_raw)

        spam_bin_tree(
            nanonet.genesis.node, spam_raw, nanonet.genesis.account, spam_count
        )

        nanonet.ensure_all_confirmed()

        pass


if __name__ == "__main__":
    unittest.main()

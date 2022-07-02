import time
import unittest
from cmath import nan
from collections import deque
from decimal import *
from itertools import chain

import nano_docker as nanotest


def distribute_voting_weight_uniform(nanonet, count, reserved):
    reps = [
        nanonet.create_node(name=f"rep_{n}").create_wallet(use_as_repr=True)
        for n in range(count)
    ]

    print("genesis balance:", nanonet.genesis.account.balance)

    balance_left = nanonet.genesis.account.balance - reserved
    assert balance_left <= nanonet.genesis.account.balance

    balance_per_rep = int(balance_left // count)
    assert balance_per_rep * count <= nanonet.genesis.account.balance

    print("balance_per_rep:", balance_per_rep)

    for rep_wallet, rep_account in reps:
        nanonet.genesis.account.print_info()

        nanonet.genesis.account.send(rep_account, balance_per_rep)
        nanonet.ensure_all_confirmed()

    return reps


def spam_bin_tree(node, amount, source_account, count):
    source_account.print_info()

    chain_root = nanotest.generate_random_account()
    chain_root.receive(source_account.send(chain_root, amount))
    nanotest.flush_block_queue(node)

    q = deque([chain_root])

    for i in range(count):
        r = q.popleft()
        a = nanotest.generate_random_account()
        b = nanotest.generate_random_account()

        half_balance = int(r.balance / 2)
        a.receive(r.send(a, half_balance))
        b.receive(r.send(b, half_balance))

        nanotest.flush_block_queue(node)

        q.append(a)
        q.append(b)

        if i % 100 == 0:
            print("spam bin_tree:", i)


class TestStringMethods(unittest.TestCase):
    def test_nano(self):
        nanonet = nanotest.initialize()

        node = nanonet.create_node()

        reserved_raw = 2**20
        reps = distribute_voting_weight_uniform(nanonet, 5, reserved_raw)

        genesis_chain = nanonet.genesis.account.to_chain()
        spam_bin_tree(
            nanonet.genesis.node,
            amount=reserved_raw,
            source_account=nanonet.genesis.account,
            count=500,
        )

        nanotest.ensure_all_confirmed()

        pass


if __name__ == "__main__":
    unittest.main()

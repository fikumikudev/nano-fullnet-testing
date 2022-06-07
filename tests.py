from itertools import chain
import unittest
from cmath import nan
from collections import deque

import nano_docker as nanotest


def spam_bin_tree(node, amount, source_account, count):
    chain_root = nanotest.Chain.random_account()
    chain_root.receive(source_account.send(chain_root, amount))
    chain_root.publish(node)

    q = deque([chain_root])

    for i in range(count):
        r = q.popleft()
        a = nanotest.Chain.random_account()
        b = nanotest.Chain.random_account()

        half_balance = int(r.balance / 2)
        a.receive(r.send(a, half_balance))
        b.receive(r.send(b, half_balance))

        r.publish(node)
        a.publish(node)
        b.publish(node)

        q.append(a)
        q.append(b)

        if i % 100 == 0:
            print("spam bin_tree:", i)


class TestStringMethods(unittest.TestCase):
    def test_nano(self):
        nano_test = nanotest.create()

        reps = [nano_test.create_node_with_account() for _ in range(2)]
        node = nano_test.create_node()

        nano_test.genesis_account.print_info()

        # uniformly distribute rep voting weight
        reserved = 2 ** 20
        balance_left = nano_test.genesis_account.balance - reserved
        balance_per_rep = int(balance_left / len(reps))
        for _, _, rep_account in reps:
            nano_test.genesis_account.send(rep_account, balance_per_rep)

        nano_test.ensure_all_confirmed()

        genesis_chain = nano_test.genesis_account.to_chain()

        spam_bin_tree(
            nano_test.genesis_node,
            amount=reserved,
            source_account=nano_test.genesis_account,
            count=500,
        )

        nano_test.ensure_all_confirmed()

        pass


if __name__ == "__main__":
    unittest.main()

import unittest

import nano_docker as nanotest

class TestStringMethods(unittest.TestCase):

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

    def test_isupper(self):
        self.assertTrue('FOO'.isupper())
        self.assertFalse('Foo'.isupper())

    def test_split(self):
        s = 'hello world'
        self.assertEqual(s.split(), ['hello', 'world'])
        # check that s.split fails when the separator is not a string
        with self.assertRaises(TypeError):
            s.split(2)

    def test_nano(self):
        nano_test = nanotest.create()

        reps = [nano_test.create_node_with_account() for _ in range(2)]
        node = nano_test.create_node()

        nano_test.genesis_account.print_info()

        # uniformly distribute rep voting weight
        reserved = 2 ^ 20
        balance_left = nano_test.genesis_account.balance - reserved
        balance_per_rep = int(balance_left / len(reps))
        for _, _, rep_account in reps:
            nano_test.genesis_account.send(rep_account, balance_per_rep) 

        nano_test.ensure_all_confirmed()

        genesis_chain = nano_test.genesis_account.to_chain()

        pass


if __name__ == '__main__':
    unittest.main()

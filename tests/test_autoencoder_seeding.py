import unittest
import numpy as np

from sentinel.engine import SentinelEngine


class AutoencoderSeedingTests(unittest.TestCase):
    def test_anagram_server_ids_produce_distinct_models(self):
        engine = SentinelEngine()
        profile_ab = engine._profile("srv-ab", dimension=10)
        profile_ba = engine._profile("srv-ba", dimension=10)
        # Naive byte-sum (sum(b) + 7) caused srv-ab and srv-ba to have identical seeds.
        # Cryptographic seeding must yield distinct initial weight matrices.
        self.assertFalse(
            np.array_equal(profile_ab.autoencoder.w1, profile_ba.autoencoder.w1),
            "Anagram server IDs must not share identical autoencoder weights",
        )
        self.assertFalse(
            np.array_equal(profile_ab.autoencoder.w2, profile_ba.autoencoder.w2),
            "Anagram server IDs must not share identical autoencoder weights",
        )

    def test_permutations_do_not_collide(self):
        engine = SentinelEngine()
        permutations = [
            "alpha-beta", "beta-alpha", "server-12", "server-21",
            "mcp-srv-01", "mcp-srv-10", "worker-xy", "worker-yx",
        ]
        profiles = [engine._profile(pid, dimension=8) for pid in permutations]
        for i in range(len(profiles)):
            for j in range(i + 1, len(profiles)):
                self.assertFalse(
                    np.array_equal(profiles[i].autoencoder.w1, profiles[j].autoencoder.w1),
                    f"Collision detected between {permutations[i]} and {permutations[j]}",
                )

    def test_seeding_is_deterministic(self):
        engine1 = SentinelEngine()
        engine2 = SentinelEngine()
        p1 = engine1._profile("server-fixed-test", dimension=12)
        p2 = engine2._profile("server-fixed-test", dimension=12)
        np.testing.assert_array_equal(p1.autoencoder.w1, p2.autoencoder.w1)
        np.testing.assert_array_equal(p1.autoencoder.w2, p2.autoencoder.w2)


if __name__ == "__main__":
    unittest.main()

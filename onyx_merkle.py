"""onyx_merkle.py — the incremental Merkle tree. The 100k foundation for signed state.

The panel's #1 catch specific to us (DeepSeek): NEVER recompute the whole Merkle root per
request — at 100k agents transacting, an O(n) rebuild per write is a 100ms+ CPU bottleneck
that collapses under load. This does it the right way:

  · set(key, value)   -> O(log n): updates ONLY the path from that leaf to the root.
  · root()            -> O(1): the current root is always cached at tree[1].
  · proof(key)        -> O(log n): a Merkle inclusion path, so ANY party can verify one
                          agent's state without the whole set (per-agent verifiability at scale).

Capacity doubles amortized; a rebuild is rare and O(n). Everything derives from these:
the Point of Truth root, the Census root, the credit-ledger balance root — all become
incremental, so a burst of 100k writes stays cheap and the root is always ready to serve.
"""
import hashlib

_ZERO = b"\x00" * 32


def _leaf(v: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + v).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


class IncrementalMerkle:
    def __init__(self):
        self.cap = 1                       # leaf capacity (power of two)
        self.tree = [_ZERO, _ZERO]         # heap array: index 1 = root, leaves at [cap .. 2cap-1]
        self.key2pos: dict[str, int] = {}  # stable leaf position per key
        self.n = 0                         # number of live leaves

    def _grow(self) -> None:
        # double capacity and rebuild the internal nodes (amortized O(1) per insert)
        new_cap = self.cap * 2
        tree = [_ZERO] * (2 * new_cap)
        for pos in range(self.n):          # copy leaves to their positions in the bigger tree
            tree[new_cap + pos] = self.tree[self.cap + pos]
        self.cap, self.tree = new_cap, tree
        for i in range(new_cap - 1, 0, -1):  # rebuild internal nodes bottom-up
            self.tree[i] = _node(self.tree[2 * i], self.tree[2 * i + 1])

    def set(self, key: str, value: bytes) -> None:
        pos = self.key2pos.get(key)
        if pos is None:
            if self.n == self.cap:
                self._grow()
            pos = self.n
            self.key2pos[key] = pos
            self.n += 1
        i = self.cap + pos
        self.tree[i] = _leaf(value)
        i //= 2
        while i >= 1:                        # walk only this leaf's path to the root — O(log n)
            self.tree[i] = _node(self.tree[2 * i], self.tree[2 * i + 1])
            i //= 2

    def root(self) -> str:
        return "0x" + self.tree[1].hex()     # O(1) — always current, never recomputed on read

    def proof(self, key: str):
        """O(log n) inclusion path: list of (sibling_hash_hex, is_right)."""
        if key not in self.key2pos:
            return None
        i = self.cap + self.key2pos[key]
        path = []
        while i > 1:
            sib = i + 1 if i % 2 == 0 else i - 1
            path.append((self.tree[sib].hex(), i % 2 == 0))  # sibling is on the right if we're the left
            i //= 2
        return path

    @staticmethod
    def verify(value: bytes, path, root_hex: str) -> bool:
        """Recompute the root from a leaf + its O(log n) path — anyone can check one agent."""
        h = _leaf(value)
        for sib_hex, sib_is_right in path:
            sib = bytes.fromhex(sib_hex)
            h = _node(h, sib) if sib_is_right else _node(sib, h)
        return ("0x" + h.hex()) == root_hex

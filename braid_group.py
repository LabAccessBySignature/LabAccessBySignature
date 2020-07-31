from sage.all import *
import random, pickle, base64, hashlib

class BraidSignGroup:
    def __init__(self, n, p, l):
        self.p = p
        self.l = l
        self.n = n
        self.B = BraidGroup(n)
        self.identityElem = self.B([])
        self.gens = self.B.generators()
        self.leftGens = [g for g in self.gens if self.gens.index(g) + 1 <= (int(n / 2) - 1)]
        self.rightGens = [g for g in self.gens if self.gens.index(g) + 1 >= (int(n / 2) + 1)]
        self.magic = 5

    def hash(self, U, m, T):
        parts = [U]
        parts.append(int("".join([str(part) for part in [elem.encode("utf-8").hex() for elem in m]]), 16))
        # parts.append(int("".join([str(part) for part in [elem.encode("hex") for elem in m]]), 16))
        parts.append(self.getIntFromBraid(T))
        return int("".join([str(part) for part in parts])) % (self.p - 1) + 1

    def hash1(self, m):
        sha = hashlib.sha256()
        sha.update(m.encode())
        hash_m = int.from_bytes(sha.digest(), "big")
        return self.B([int(d) % (self.B.strands() - 1) + 1 for d in str(abs(hash_m))])

    def getPowForLeftForm(self, leftForm):
        deltaPower = leftForm[0]
        if deltaPower == self.identityElem:
            return 0
        else:
            return deltaPower.exponent_sum() / self.B.delta().exponent_sum()

    def getIntFromBraid(self, braid):
        leftForm = braid.left_normal_form()
        parts = [self.getPowForLeftForm(leftForm)]
        for i in range(1, len(leftForm)):
            parts.append(int("".join([str(digit) for digit in leftForm[i].permutation()])))
        return int("".join([str(part) for part in parts]))

    def ifFromSubgroupL(self, braid):
        leftForm = braid.left_normal_form()
        inf = self.getPowForLeftForm(leftForm)
        sup = inf + len(leftForm) - 1
        if (0 <= inf and inf <= sup and sup <= self.l):
            return True
        return False

    def randLBElement(self):
        r = random.randint(1, self.magic)
        e = self.identityElem
        for i in range(0, r):
            e *= random.choice(self.leftGens)
        return e

    def randRBElement(self):
        r = random.randint(1, self.magic)
        e = self.identityElem
        for i in range(0, r):
            e *= random.choice(self.rightGens)
        return e

    def randLBlElement(self):
        while True:
            elem = self.randLBElement()
            if (self.ifFromSubgroupL(elem)):
                return elem

    def randRBlElement(self):
        while True:
            elem = self.randRBElement()
            if (self.ifFromSubgroupL(elem)):
                return elem

    def serializeBraid(self, x):
        return base64.b64encode(pickle.dumps(x)).decode()

    def deserializeBraid(self, x):
        return pickle.loads(base64.b64decode(x))
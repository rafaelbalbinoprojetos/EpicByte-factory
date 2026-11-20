import unittest

from calculadora import multiplicar, somar


class TestCalculadora(unittest.TestCase):
    def test_somar_positivos(self):
        self.assertEqual(somar(2, 3), 5)

    def test_somar_negativos(self):
        self.assertEqual(somar(-2, -3), -5)

    def test_somar_zero(self):
        self.assertEqual(somar(7, 0), 7)

    def test_multiplicar_positivos(self):
        self.assertEqual(multiplicar(4, 3), 12)

    def test_multiplicar_negativo(self):
        self.assertEqual(multiplicar(-4, 3), -12)

    def test_multiplicar_zero(self):
        self.assertEqual(multiplicar(7, 0), 0)


if __name__ == "__main__":
    unittest.main()

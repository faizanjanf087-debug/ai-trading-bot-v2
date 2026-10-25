"""V2.11: error ki saaf hint (logs mein wajah + hal)."""
import unittest

from services.diagnostics import HINTS, describe, hint_for


# telegram library ke errors ka naam hi chahiye (library ke bina bhi test chale)
class Conflict(Exception):
    pass


class InvalidToken(Exception):
    pass


class NetworkError(Exception):
    pass


class TimedOut(Exception):
    pass


class DiagnosticsTests(unittest.TestCase):
    def test_conflict_hint(self):
        self.assertEqual(hint_for(Conflict("terminated by other getUpdates request")), HINTS["conflict"])

    def test_invalid_token_hint(self):
        self.assertEqual(hint_for(InvalidToken()), HINTS["token"])

    def test_ssl_hint_from_network_error(self):
        e = NetworkError("CERTIFICATE_VERIFY_FAILED: self-signed certificate in chain")
        self.assertEqual(hint_for(e), HINTS["ssl"])

    def test_timeout_is_network_hint(self):
        self.assertEqual(hint_for(TimedOut()), HINTS["network"])

    def test_missing_library_hint(self):
        self.assertEqual(hint_for(ModuleNotFoundError("No module named 'telegram'")), HINTS["library"])

    def test_unknown_error_has_no_hint(self):
        self.assertIsNone(hint_for(ValueError("kuch aur")))

    def test_describe_includes_type_and_hint(self):
        line = describe(Conflict("x"))
        self.assertIn("Conflict", line)
        self.assertIn("HINT:", line)
        self.assertEqual(describe(None), "unknown error")


if __name__ == "__main__":
    unittest.main()

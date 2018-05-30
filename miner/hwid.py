import base64
import os

ENCODED_LENGTH = 12


def generate() -> str:
    """
    Generate unique HW identifier

    :return:
        String with unique HW identifier.
    """
    return base64.b64encode(os.urandom(ENCODED_LENGTH), b'ab').decode('ascii')

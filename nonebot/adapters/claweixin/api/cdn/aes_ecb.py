from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BLOCK_SIZE = 16


def pkcs7_pad(data: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    padding = block_size - (len(data) % block_size)
    return data + bytes([padding]) * padding


def pkcs7_unpad(data: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    if not data or len(data) % block_size != 0:
        raise ValueError("invalid AES-ECB payload length")
    padding = data[-1]
    if padding < 1 or padding > block_size:
        raise ValueError("invalid PKCS7 padding")
    if data[-padding:] != bytes([padding]) * padding:
        raise ValueError("invalid PKCS7 padding bytes")
    return data[:-padding]


def aes_ecb_padded_size(size: int, block_size: int = BLOCK_SIZE) -> int:
    return ((size // block_size) + 1) * block_size


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    padded = pkcs7_pad(data)
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_aes_ecb(data: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(data) + decryptor.finalize()
    return pkcs7_unpad(decrypted)

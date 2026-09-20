from cryptography import x509

from app.crypto import generate_csr_pem, generate_private_key


def test_generate_csr_pem_is_valid_and_signature_verifies():
    key = generate_private_key()
    csr_pem = generate_csr_pem(key, common_name="test-node")

    csr = x509.load_pem_x509_csr(csr_pem.encode())
    assert csr.is_signature_valid
    cn = csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
    assert cn == "test-node"

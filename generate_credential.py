import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate, load_der_x509_certificate

def generate_security_credential(operator_password, cert_path):
    with open(cert_path, "rb") as cert_file:
        cert_data = cert_file.read()
        
        # Safaricom certificates are often in PEM format, despite the .cer extension.
        # We try to load it as PEM first.
        try:
            cert = load_pem_x509_certificate(cert_data, default_backend())
        except ValueError:
            # If it fails, we fall back to attempting a DER binary load
            try:
                cert = load_der_x509_certificate(cert_data, default_backend())
            except Exception as e:
                raise ValueError("Could not parse the certificate. Make sure the file is valid and not corrupted.") from e

        public_key = cert.public_key()

    # Encrypt the password using RSA algorithm and PKCS1v15 padding
    encrypted_password = public_key.encrypt(
        operator_password.encode('utf-8'),
        padding.PKCS1v15()
    )
    
    # Convert the resulting encrypted byte array into a base64 encoded string
    return base64.b64encode(encrypted_password).decode('utf-8')

# --- CONFIGURATION ---
operator_password = "Delstarford@123" 
certificate_file = "ProductionCertificate.cer" 

try:
    security_credential = generate_security_credential(operator_password, certificate_file)
    print("\nSUCCESS! Copy the string below and paste it into your .env file:")
    print("=" * 60)
    print(f"DARAJA_SECURITY_CREDENTIAL={security_credential}")
    print("=" * 60)
except FileNotFoundError:
    print("Error: Could not find the certificate file. Ensure 'ProductionCertificate.cer' is in the same folder as this script.")
except Exception as e:
    print(f"An error occurred: {e}")
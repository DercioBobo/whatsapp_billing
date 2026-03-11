from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="whatsapp_billing",
    version="0.0.1",
    description="Automated WhatsApp/USSD session billing for ERPNext",
    author="Your Company",
    author_email="info@example.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)

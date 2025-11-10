try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib

from setuptools import find_packages, setup

HERE = pathlib.Path(__file__).parent
FILE = HERE / "README.md"
try:
    README = FILE.read_text()
except AttributeError:
    README = FILE.open().read().split("\n")

version = "9.2.3"

setup(
    name="ls_message_parsing",
    version=version,
    description="Loadsensing parsing library",
    long_description_content_type="text/markdown",
    long_description=README,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    package_data={
        '': ['pytransform/_pytransform.so'],
    },
    data_files=[
        (
            "dig_cfg",
            [
                "ls_message_parsing/messages/output/digital/GenericModbusDataCfgs/generic_modbus_configs.json"
            ],
        )
    ],
    install_requires=[
        "pycryptodome",
        "bitstring==3.1.9",
        "six==1.16.0",
        'singledispatch==3.7.0; python_version <= "2.7"',
        'typing==3.10.0.0 ; python_version <= "2.7"',
    ],
)

from setuptools import find_packages, setup

setup(
    name="dojinvoice_db",
    version="0.0.3",
    description="Make DB of Dojinvoice",
    description_content_type="",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url="https://github.com/eggplants/dojinvoice_db",
    author="eggplants",
    packages=find_packages(),
    include_package_data=True,
    license='MIT',
    install_requires=open('requirements.txt').read().splitlines(),
    entry_points={
        "console_scripts": [
            "dvdb=main:main"
        ]
    }
)

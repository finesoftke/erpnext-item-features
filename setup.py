from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in itemfeatures/__init__.py
from itemfeatures import __version__ as version

setup(
	name="itemfeatures",
	version=version,
	description="Add item features to Item and update BOM",
	author="Finesoft Afrika",
	author_email="macharianyota@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)

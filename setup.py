import re
from setuptools import setup


version = re.search("__version__ = '([^']+)'",
                    open('skip/__init__.py').read()).group(1)

setup(name = 'skip',
      version = version,
      author = 'Tim Radvan',
      author_email = 'blob8108@gmail.com',
      url = 'https://github.com/blob8108/skip',
      description = 'a Python Scratch Interpreter based on Kurt',
      install_requires = ['kurt >=2.0, <3.0',],
      license = 'MIT',
      packages = ['skip'],
      scripts = ['skip_pygame.py'],
      classifiers = [
          "Programming Language :: Python",
      ],
)
 

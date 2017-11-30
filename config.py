import os
REPODIR = os.path.join(os.path.dirname(__file__),'repos')
CACHEDIR = os.path.join(os.path.dirname(__file__),'cache')
DEFAULT_TARGET_BRANCH='master'
SUBMODULES = {}
REVS_TO_CHECK_BACK=100
from local_config import *

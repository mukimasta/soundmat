import pytest

from soundmat.config import load_config
from soundmat.supervisor import Options, Supervisor


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def make_sup(config, tmp_path):
    """建立一个使用临时数据目录的运行管理；默认使用虚拟垫子和记录型引擎。"""
    made = []

    def make(**kw):
        kw.setdefault("virtual", True)
        kw.setdefault("data_dir", tmp_path / "data")
        kw.setdefault("seed", 1)
        s = Supervisor(config, Options(**kw))
        made.append(s)
        return s

    yield make
    for s in made:
        s.stop()

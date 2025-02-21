import inspect

from pathlib import Path
from copy import copy
from unittest.mock import ANY

import pytest
import nbformat
from IPython.core.interactiveshell import InteractiveShell

from conftest import _make_nb
from ploomber_engine.ipython import PloomberShell, PloomberClient
from ploomber_engine import ipython


def test_captures_display_data():
    shell = PloomberShell()

    code = """
import matplotlib.pyplot as plt
plt.plot([1, 2, 3])
"""

    shell.run_cell(code)

    output = shell._get_output()

    assert output == [
        {
            "output_type": "execute_result",
            "metadata": {},
            "data": {
                "text/plain": ANY,
            },
            "execution_count": None,
        },
        {
            "output_type": "display_data",
            "metadata": {},
            "data": {"text/plain": ANY, "image/png": ANY},
        },
    ]


def test_client_captures_display_data():
    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell(
        source="""
import matplotlib.pyplot as plt
plt.plot([1, 2, 3])
"""
    )
    nb.cells.append(cell)

    with PloomberClient(nb) as client:
        result = client.execute_cell(
            cell, cell_index=0, execution_count=0, store_history=False
        )

    assert len(result) == 2


def test_client_captures_all_outputs():
    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell(
        source="""
import matplotlib.pyplot as plt
print('hello')
plt.plot([1, 2, 3])
'bye'
"""
    )
    nb.cells.append(cell)

    with PloomberClient(nb) as client:
        result = client.execute_cell(
            cell, cell_index=0, execution_count=0, store_history=False
        )

    assert len(result) == 3


def test_reports_exceptions():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(
        nbformat.v4.new_code_cell(
            source="""
def crash():
    raise ValueError("something went wrong")

crash()
"""
        )
    )

    with pytest.raises(ValueError) as excinfo:
        PloomberClient(nb).execute()

    assert str(excinfo.value) == "something went wrong"
    assert nb.cells[0].outputs[0] == {
        "output_type": "error",
        "ename": "ValueError",
        "evalue": "something went wrong",
        "traceback": ANY,
    }
    assert "something went wrong" in "\n".join(nb.cells[0].outputs[0]["traceback"])


def test_displays_then_raises_exception():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(
        nbformat.v4.new_code_cell(
            source="""
print("hello!")
print("hello!")

def crash():
    raise ValueError("something went wrong")

crash()
"""
        )
    )

    with pytest.raises(ValueError) as excinfo:
        PloomberClient(nb).execute()

    assert str(excinfo.value) == "something went wrong"
    assert nb.cells[0].outputs == [
        {"output_type": "stream", "name": "stdout", "text": "hello!\nhello!"},
        {
            "output_type": "error",
            "ename": "ValueError",
            "evalue": "something went wrong",
            "traceback": ANY,
        },
    ]
    assert "something went wrong" in "\n".join(nb.cells[0].outputs[1]["traceback"])


def test_client_execute(tmp_assets):
    nb = nbformat.read(
        tmp_assets / "different-outputs.ipynb", as_version=nbformat.NO_CONVERT
    )
    client = PloomberClient(nb)
    nb_out = client.execute()

    # this will complain if the notebook is not well formatted
    nbformat.write(nb_out, "out.ipynb", version=nbformat.NO_CONVERT)

    assert nb_out.cells[0]["outputs"] == [
        {
            "output_type": "execute_result",
            "metadata": {},
            "data": {"text/plain": "3"},
            "execution_count": 1,
        }
    ]

    assert nb_out.cells[1]["outputs"] == [
        {"output_type": "stream", "name": "stdout", "text": "stuff\n"},
    ]

    assert nb_out.cells[2]["outputs"] == [
        {"output_type": "stream", "name": "stdout", "text": "a\nb\n"},
        {
            "output_type": "execute_result",
            "metadata": {},
            "data": {"text/plain": "2"},
            "execution_count": 3,
        },
    ]

    assert nb_out.cells[3]["outputs"] == [
        {
            "output_type": "execute_result",
            "metadata": {},
            "data": {
                "text/plain": ANY,
            },
            "execution_count": 4,
        },
        {
            "output_type": "display_data",
            "metadata": {},
            "data": {
                "text/plain": ANY,
                "image/png": ANY,
            },
        },
    ]


def test_client_gets_clean_shell():
    nb1 = nbformat.v4.new_notebook()
    nb1.cells.append(nbformat.v4.new_code_cell(source="some_variable = 1"))
    PloomberClient(nb1).execute()

    nb2 = nbformat.v4.new_notebook()
    nb2.cells.append(nbformat.v4.new_code_cell(source="print(some_variable)"))

    with pytest.raises(NameError):
        PloomberClient(nb2).execute()


def test_output_to_sys_stderr():
    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell(
        source="""
import sys
print('error', file=sys.stderr)
"""
    )
    nb.cells.append(cell)

    out = PloomberClient(nb).execute()

    assert out.cells[0]["outputs"] == [
        {"output_type": "stream", "name": "stderr", "text": "error\n"},
    ]


def test_displays_html_repr():
    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell(
        source="""
import pandas as pd
pd.DataFrame({'x': [1, 2, 3]})
"""
    )
    nb.cells.append(cell)

    out = PloomberClient(nb).execute()

    assert out.cells[0]["outputs"] == [
        {
            "output_type": "execute_result",
            "metadata": {},
            "data": {
                "text/plain": "   x\n0  1\n1  2\n2  3",
                "text/html": ANY,
            },
            "execution_count": 1,
        }
    ]


def test_matplotlib_is_optional(monkeypatch):
    # raise ModuleNotFoundError when importing matplotlib
    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "matplotlib":
            raise ModuleNotFoundError
        else:
            return __import__(
                name, globals=globals, locals=locals, fromlist=fromlist, level=level
            )

    builtins = copy(ipython.__builtins__)
    builtins["__import__"] = mock_import

    # path builtins in ipython modfule
    monkeypatch.setattr(ipython, "__builtins__", builtins)

    # should not raise ModuleNotFoundError
    assert PloomberShell()


def test_adds_execution_count():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell())
    nb.cells.append(nbformat.v4.new_code_cell())
    out = PloomberClient(nb).execute()

    assert [c["execution_count"] for c in out.cells] == [1, 2]


def test_keeps_same_std_out_err_order_as_jupyter():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell())
    nb.cells.append(nbformat.v4.new_code_cell())
    out = PloomberClient(nb).execute()

    assert [c["execution_count"] for c in out.cells] == [1, 2]


def test_ignores_non_code_cells():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_markdown_cell("this is markdown"))
    nb.cells.append(nbformat.v4.new_code_cell("1 + 1"))
    out = PloomberClient(nb).execute()

    assert out.cells[1] == {
        "id": ANY,
        "cell_type": "code",
        "metadata": {"ploomber": {"timestamp_start": ANY, "timestamp_end": ANY}},
        "execution_count": 1,
        "source": "1 + 1",
        "outputs": [
            {
                "output_type": "execute_result",
                "metadata": {},
                "data": {"text/plain": "2"},
                "execution_count": 1,
            },
        ],
    }


@pytest.mark.parametrize(
    "source, expected",
    [
        [
            "from IPython.display import HTML; HTML('<br>some html</br>')",
            {
                "output_type": "execute_result",
                "metadata": {},
                "data": {
                    "text/plain": "<IPython.core.display.HTML object>",
                    "text/html": "<br>some html</br>",
                },
                "execution_count": 1,
            },
        ],
        [
            "from IPython.display import Markdown; Markdown('# some md')",
            {
                "output_type": "execute_result",
                "metadata": {},
                "data": {
                    "text/plain": "<IPython.core.display.Markdown object>",
                    "text/markdown": "# some md",
                },
                "execution_count": 1,
            },
        ],
        [
            "from IPython.display import JSON; JSON(dict(a=1))",
            {
                "output_type": "execute_result",
                "metadata": {"application/json": {"expanded": False, "root": "root"}},
                "data": {
                    "text/plain": "<IPython.core.display.JSON object>",
                    "application/json": {"a": 1},
                },
                "execution_count": 1,
            },
        ],
        [
            "from IPython.display import Javascript; Javascript('let x = 1')",
            {
                "output_type": "execute_result",
                "metadata": {},
                "data": {
                    "text/plain": "<IPython.core.display.Javascript object>",
                    "application/javascript": "let x = 1",
                },
                "execution_count": 1,
            },
        ],
        [
            "from IPython.display import Latex; Latex('$ x = 1$')",
            {
                "output_type": "execute_result",
                "metadata": {},
                "data": {
                    "text/plain": "<IPython.core.display.Latex object>",
                    "text/latex": "$ x = 1$",
                },
                "execution_count": 1,
            },
        ],
    ],
    ids=[
        "html",
        "md",
        "json",
        "js",
        "latex",
    ],
)
def test_display_formats(source, expected):
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(source=source))
    out = PloomberClient(nb).execute()

    assert out.cells[0]["outputs"][0] == expected


def test_adds_current_directory_to_sys_path(tmp_empty, no_sys_modules_cache):
    Path("some_new_module.py").write_text(
        """
def x():
    pass
"""
    )

    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(source="import some_new_module"))

    assert PloomberClient(nb).execute()


def test_context_manager():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(source="1 + 1"))

    with PloomberClient(nb) as client:
        client._shell.user_ns["a"] = 1
        client._execute()


def test_clears_instance_execute():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(source="1 + 1"))

    c = PloomberClient(nb)
    c.execute()

    assert PloomberShell._instance is None
    assert InteractiveShell._instance is None


def test_clears_instance_execute_cell():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(source="1 + 1"))

    with PloomberClient(nb) as client:
        client.execute_cell(
            nb.cells[0], cell_index=0, execution_count=0, store_history=False
        )

    assert PloomberShell._instance is None
    assert InteractiveShell._instance is None


# create code cell
def cell(source):
    return nbformat.v4.new_code_cell(source=source)


def test_get_namespace():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(cell("x = 1"))
    nb.cells.append(
        cell(
            """
class SomeClass:
    pass

some_object = SomeClass()
"""
        )
    )
    nb.cells.append(
        cell(
            """
def add(x, y):
    return x + y

result = add(100, 200)
"""
        )
    )

    ns = PloomberClient(nb).get_namespace()

    assert set(ns) == {"SomeClass", "add", "result", "some_object", "x"}
    assert inspect.isclass(ns["SomeClass"])
    assert isinstance(ns["some_object"], ns["SomeClass"])
    assert ns["x"] == 1
    assert ns["add"](1, 2) == 3
    assert ns["result"] == 300


def test_get_definitions():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(cell("x = 1"))
    nb.cells.append(
        cell(
            """
class SomeClass:
    pass

raise ValueError('some error happened')

some_object = SomeClass()
"""
        )
    )
    nb.cells.append(
        cell(
            """
def add(x, y):
    return x + y


raise ValueError('another error happened')

result = add(100, 200)
"""
        )
    )
    defs = PloomberClient(nb).get_definitions()

    assert set(defs) == {"SomeClass", "add"}
    assert inspect.isclass(defs["SomeClass"])
    assert defs["add"](1, 2) == 3


def test_from_path(tmp_empty):
    nb = nbformat.v4.new_notebook()
    nb.cells.append(cell("x = 1"))
    Path("nb.ipynb").write_text(nbformat.writes(nb), encoding="utf-8")

    ns = PloomberClient.from_path("nb.ipynb").get_namespace()

    assert ns == dict(x=1)


def test_shell_clears_instance():
    with PloomberShell() as shell:
        shell.run_cell("1 + 1")

    assert PloomberShell._instance is None
    assert InteractiveShell._instance is None


def test_flushing():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(cell("import sys"))
    nb.cells.append(cell("sys.stderr.flush()"))
    nb.cells.append(cell("sys.stdout.flush()"))
    PloomberClient(nb).execute()


def test_io():
    io = ipython.IO()

    io.write("a")
    io.writelines(["b", "c"])

    assert io.get_separated_values() == ["a", "b", "c"]
    assert io.getvalue() == "abc"


def test_log_print_statements(capsys):
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_code_cell(source='print("a")'),
        nbformat.v4.new_code_cell(source='print("b")'),
    ]

    PloomberClient(nb, display_stdout=True, progress_bar=False).execute()

    captured = capsys.readouterr()
    assert captured.out == "a\nb\n"


def test_log_print_statements_init_from_path(tmp_empty, capsys):
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_code_cell(source='print("a")'),
        nbformat.v4.new_code_cell(source='print("b")'),
    ]

    nbformat.write(nb, "notebook.ipynb")

    PloomberClient.from_path(
        "notebook.ipynb", display_stdout=True, progress_bar=False
    ).execute()

    captured = capsys.readouterr()
    assert captured.out == "a\nb\n"


@pytest.mark.parametrize(
    "nb, idx_injected, idx_out",
    [
        [_make_nb(["print(x + y)"]), 0, 1],
        [_make_nb(["1 + 1", "print(x + y)"]), 0, 2],
        [_make_nb(["#PARAMETERS\n1 + 2", "print(x + y)"]), 1, 2],
    ],
)
def test_parametrize(tmp_empty, nb, idx_injected, idx_out):
    client = PloomberClient(nb)
    out = client.execute(parameters=dict(x=21, y=21))

    assert out.cells[idx_out]["outputs"][0]["text"] == "42\n"
    assert out.cells[idx_injected].source == "# Injected parameters\nx = 21\ny = 21\n"


def test_progress_bar(tmp_empty, capsys):
    nb = _make_nb(["1 + 1"], path=None)

    client = PloomberClient(nb)
    client.execute()

    captured = capsys.readouterr()
    assert "Executing cell: 1" in captured.err


@pytest.mark.parametrize(
    "debug_later, path",
    [
        [True, "jupyter.dump"],
        ["custom.dump", "custom.dump"],
        ["path/to/file.dump", "path/to/file.dump"],
    ],
)
def test_execute_notebook_debug_later(tmp_empty, debug_later, path):
    nb = _make_nb(["x = 1", "y = 0", "x / y"])
    client = PloomberClient(nb, debug_later=debug_later)

    with pytest.raises(ZeroDivisionError):
        client.execute()

    assert Path(path).is_file()

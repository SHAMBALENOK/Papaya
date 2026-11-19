import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

import os  # noqa: E402

os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh.list_parser import (  # noqa: E402
    _number_is_out_of_order as g,
    _starts_new_olympiad as f,
)

assert f('Отраслевая олимпиада школьников «Газпром»')
assert f('XIX Южно-Российская межрегиональная олимпиада')
assert not f('интеллекту (с возможностью участия иностранных обучающихся)')
assert not f('школьников «Газпром»')
assert not f('межрегиональная олимпиада школьников')
assert g('19', 18) is False
assert g('19', 19) is True
assert g('12', 19) is True
assert g('1', None) is False
print('helpers ok')

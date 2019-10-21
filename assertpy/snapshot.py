# Copyright (c) 2015-2019, Activision Publishing, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import datetime
import inspect
import json


class SnapshotMixin(object):
    """Snapshot mixin."""

    def snapshot(self, id=None, path='__snapshots'):
        if sys.version_info[0] < 3:
            raise NotImplementedError('snapshot testing requires Python 3')

        class _Encoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, set):
                    return {'__type__': 'set', '__data__': list(o)}
                elif isinstance(o, complex):
                    return {'__type__': 'complex', '__data__': [o.real, o.imag]}
                elif isinstance(o, datetime.datetime):
                    return {'__type__': 'datetime', '__data__': o.strftime('%Y-%m-%d %H:%M:%S')}
                elif '__dict__' in dir(o) and type(o) is not type:
                    return {
                        '__type__': 'instance',
                        '__class__': o.__class__.__name__,
                        '__module__': o.__class__.__module__,
                        '__data__': o.__dict__
                    }
                return json.JSONEncoder.default(self, o)

        class _Decoder(json.JSONDecoder):
            def __init__(self):
                json.JSONDecoder.__init__(self, object_hook=self.object_hook)

            def object_hook(self, d):
                if '__type__' in d and '__data__' in d:
                    if d['__type__'] == 'set':
                        return set(d['__data__'])
                    elif d['__type__'] == 'complex':
                        return complex(d['__data__'][0], d['__data__'][1])
                    elif d['__type__'] == 'datetime':
                        return datetime.datetime.strptime(d['__data__'], '%Y-%m-%d %H:%M:%S')
                    elif d['__type__'] == 'instance':
                        mod = __import__(d['__module__'], fromlist=[d['__class__']])
                        klass = getattr(mod, d['__class__'])
                        inst = klass.__new__(klass)
                        inst.__dict__ = d['__data__']
                        return inst
                return d

        def _save(name, val):
            with open(name, 'w') as fp:
                json.dump(val, fp, indent=2, separators=(',', ': '), sort_keys=True, cls=_Encoder)

        def _load(name):
            with open(name, 'r') as fp:
                return json.load(fp, cls=_Decoder)

        def _name(path, name):
            try:
                return os.path.join(path, 'snap-%s.json' % name.replace(' ','_').lower())
            except Exception:
                raise ValueError('failed to create snapshot filename, either bad path or bad name')

        if id:
            # custom id
            snapname = _name(path, id)
        else:
            # make id from filename and line number
            f = inspect.currentframe()
            fpath = os.path.basename(f.f_back.f_code.co_filename)
            fname = os.path.splitext(fpath)[0]
            lineno = str(f.f_back.f_lineno)
            snapname = _name(path, fname)

        if not os.path.exists(path):
            os.makedirs(path)

        if os.path.isfile(snapname):
            # snap exists, so load
            snap = _load(snapname)

            if id:
                # custom id, so test
                return self.is_equal_to(snap)
            else:
                if lineno in snap:
                    # found sub-snap, so test
                    return self.is_equal_to(snap[lineno])
                else:
                    # lineno not in snap, so create sub-snap and pass
                    snap[lineno] = self.val
                    _save(snapname, snap)
        else:
            # no snap, so create and pass
            _save(snapname, self.val if id else {lineno: self.val})

        return self

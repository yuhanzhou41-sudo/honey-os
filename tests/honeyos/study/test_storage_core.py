from pathlib import Path
from honeyos.study.storage import MANIFEST_NAME, StudyStorageManager

def manager(tmp_path):
    return StudyStorageManager(tmp_path/'D'/'Study', tmp_path/'D'/'StudyLibrary', tmp_path/'mnt')

def test_default_on_d_like_root(tmp_path):
    m=manager(tmp_path); m.initialize(); rows=m.list_libraries(discover=False)
    assert len(rows)==1 and rows[0]['mode']=='default' and rows[0]['online'] is True
    root=Path(rows[0]['root']); assert (root/MANIFEST_NAME).is_file()
    for d in ('resources','derived','index','temp'): assert (root/d).is_dir()

def test_portable_rediscovery_after_drive_letter_change(tmp_path):
    m=manager(tmp_path); m.initialize(); e=tmp_path/'mnt'/'e'/'HoneyOS-Study-Library'
    created=m.create_library(e,'医学教材库',removable=True); lid=created['library_id']
    f=tmp_path/'mnt'/'f'/'HoneyOS-Study-Library'; f.parent.mkdir(parents=True); e.rename(f)
    found=m.discover_external_libraries(); assert any(x['library_id']==lid for x in found)
    assert Path(m.describe(lid)['root'])==f.resolve()

def test_cleanup_never_deletes_original(tmp_path):
    m=manager(tmp_path); m.initialize(); row=m.list_libraries(discover=False)[0]; root=Path(row['root'])
    original=root/'resources'/'book'/'original.pdf'; original.parent.mkdir(parents=True); original.write_bytes(b'book')
    derived=root/'derived'/'book.bin'; derived.write_bytes(b'x'*100)
    temp=root/'temp'/'tmp.bin'; temp.write_bytes(b'y'*100)
    m.cleanup(row['library_id'],'all_derived')
    assert original.read_bytes()==b'book'; assert not derived.exists(); assert not temp.exists()

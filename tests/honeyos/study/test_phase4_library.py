from honeyos.files.service import AttachmentService
from honeyos.study.repository import StudyRepository, StudyResourceNotFoundError
from honeyos.study.service import StudyService


def make_service(tmp_path):
    return StudyService(repository=StudyRepository(tmp_path))


def upload_text(tmp_path, text='mitosis chromosome spindle'):
    return AttachmentService(tmp_path / 'files').upload_bytes(
        text.encode('utf-8'), original_filename='cell-cycle.md',
        declared_mime_type='text/markdown', source_type='study')


def test_resource_round_trip_search_delete(tmp_path):
    service=make_service(tmp_path); attachment=upload_text(tmp_path)
    resource=service.create_resource({'attachment_id':attachment.id,'title':'Cell cycle','resource_type':'notes','course_or_subject':'Biology','metadata':{'chapter':2}})
    assert service.get_resource(resource.id).title == 'Cell cycle'
    hits=service.search_resources(query='chromosome')
    assert hits and hits[0]['resource_id'] == resource.id
    assert 'mitosis chromosome spindle' in service.get_resource_content(resource.id)['extracted_text']
    service.delete_resource(resource.id)
    try: service.get_resource(resource.id)
    except StudyResourceNotFoundError: pass
    else: raise AssertionError('resource should be deleted')
    assert service.attachments.get(attachment.id).id == attachment.id


def test_course_filter_and_metadata_reindex(tmp_path):
    service=make_service(tmp_path)
    a1=upload_text(tmp_path,'renal physiology nephron')
    a2=AttachmentService(tmp_path/'files').upload_bytes(b'renal pathology glomerulus', original_filename='path.txt', declared_mime_type='text/plain', source_type='study')
    r1=service.create_resource({'attachment_id':a1.id,'title':'Physiology','resource_type':'notes','course_or_subject':'Physiology'})
    r2=service.create_resource({'attachment_id':a2.id,'title':'Pathology','resource_type':'notes','course_or_subject':'Pathology'})
    assert [h['resource_id'] for h in service.search_resources(query='renal',course_or_subject='Pathology')] == [r2.id]
    service.update_resource(r1.id, {'title':'Kidney physiology'})
    assert any(h['resource_id']==r1.id for h in service.search_resources(query='Kidney'))


def test_deleted_attachment_rejected(tmp_path):
    service=make_service(tmp_path); a=upload_text(tmp_path); service.attachments.soft_delete(a.id)
    try: service.create_resource({'attachment_id':a.id,'title':'X','resource_type':'notes'})
    except ValueError as exc: assert 'deleted attachment' in str(exc)
    else: raise AssertionError('expected ValueError')


def test_binary_pdf_rejected_in_phase4_1(tmp_path):
    service=make_service(tmp_path)
    a=AttachmentService(tmp_path/'files').upload_bytes(b'%PDF-1.7 fake', original_filename='book.pdf', declared_mime_type='application/pdf', source_type='study')
    try: service.create_resource({'attachment_id':a.id,'title':'Book','resource_type':'pdf'})
    except ValueError as exc: assert 'binary/PDF extraction is not enabled yet' in str(exc)
    else: raise AssertionError('expected ValueError')

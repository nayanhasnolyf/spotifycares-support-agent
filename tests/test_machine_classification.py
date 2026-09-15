"""Synthetic-only compatibility and bounded-experiment tests; no API calls."""
import json
from pathlib import Path
import pytest
from test_annotation import annotation_config
from test_groq_annotation import ready, retain
from test_machine_annotation import fake
from spotify_cares.annotation import AnnotationError
from spotify_cares.machine_annotation import (
    MachineClassification, MachineDecision, machine_annotate, load_events,
    prepare_run, digest, canonical, combined_machine_manifest,
)


def simple(**kwargs):
    return canonical({'primary_intent':'other_or_unclear','should_escalate':'no',
                      'escalation_reason_code':None,'ambiguity':'ambiguous',
                      'rationale':'Synthetic unclear request; clarification is possible.'}), 'synthetic'


def test_optional_guidance_and_legacy_schema():
    obj=MachineClassification.model_validate_json(simple()[0])
    assert obj.expected_reply_guidance is None
    assert 'risk_flags' not in obj.model_dump()  # absent is not a negative risk label
    with pytest.raises(ValueError):
        MachineClassification.model_validate({**obj.model_dump(),'should_escalate':'yes'})
    with pytest.raises(ValueError):
        MachineClassification.model_validate({**obj.model_dump(),'rationale':' '})


def test_new_run_preserves_old_schema_and_retained_outputs(annotation_config):
    c=ready(annotation_config)
    old=machine_annotate(c,'training',model='synthetic',provider=fake)
    raw=Path(old['path']).read_bytes(); retain(c,old)
    c.annotation.machine_decision_schema='classification-v1'
    *_,schema,provenance,path=prepare_run(c,'development',None,None,'groq')
    assert set(schema['properties'])=={'primary_intent','should_escalate','escalation_reason_code','ambiguity','rationale'}
    report=machine_annotate(c,'development',provider_name='groq',provider=simple)
    assert isinstance(load_events(Path(report['path']))[0].decision,MachineClassification)
    assert isinstance(load_events(Path(old['path']))[0].decision,MachineDecision)
    assert combined_machine_manifest(c,'training',provider_name='groq')['retained_successes']==1
    assert Path(old['path']).read_bytes()==raw
    # Gemini stays supported without pairing the small schema with old field instructions.
    _, _, _, system, _, _, _ = prepare_run(c, 'development', None, None, 'gemini')
    assert 'annotation_notes' not in system.split('TAXONOMY')[0]
    assert 'rationale' in system.split('TAXONOMY')[0]


def test_one_attempt_selection_and_no_implicit_retries(annotation_config):
    c=ready(annotation_config); c.annotation.machine_decision_schema='classification-v1'
    *_,p,path=prepare_run(c,'training',None,None,'groq')
    selection=c.annotation.output_dir/'synthetic_selection.json'
    selection.write_text(canonical({'queue_name':'training','run_sha256':digest(p),
                                    'example_ids':['train_1'],'one_attempt_per_example':True}))
    calls=[]
    def invalid(**kw):
        calls.append(1); return 'bad JSON',None
    first=machine_annotate(c,'training',provider_name='groq',provider=invalid,selection_path=selection)
    assert first['unresolved_failures']==1
    before=path.read_bytes()
    machine_annotate(c,'training',provider_name='groq',provider=invalid,selection_path=selection)
    assert len(calls)==1 and path.read_bytes()==before


def test_generated_guidance_is_rejected_but_storage_can_read_it(annotation_config):
    c=ready(annotation_config); c.annotation.machine_decision_schema='classification-v1'
    obj=json.loads(simple()[0]); obj['expected_reply_guidance']='Synthetic optional stored guidance'
    assert MachineClassification.model_validate(obj).expected_reply_guidance
    result=machine_annotate(c,'training',provider_name='groq',provider=lambda **kw:(canonical(obj),None))
    assert result['unresolved_failures']==1

"""Non-shipping synthetic headers/provenance; never Blender geometry evidence."""
from dataclasses import replace
from hashlib import sha256
import json

from fixtures.project_reference_contract import ReferenceFixture
from ucc.core.expression_library import build_expression_manifest, source_intent, canonical_digest
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.expressions import ExpressionState, DEFAULTS
from ucc.core.hand_parts import build_hand_library_recipe, build_hand_manifest, build_hand_receipt, hand_asset_id
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import PartInstance
from ucc.jobs.animation_reference_storage import publish_source_binding
from ucc.jobs.expression_storage import install_master_copy, publish_library
from ucc.jobs.hand_storage import publish_asset, publish_manifest, publish_hand_receipt, load_hand_library


class ReferenceMasterFixture(ReferenceFixture):
    def __init__(self, root, *, hand=True):
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root)
        current = self.store.load()
        prepared = root/'unit-prepared.blend'; prepared.write_bytes(b'BLENDER'+b'NOT_REAL_PREPARED_GEOMETRY'*100)
        prepared_sha = sha256(prepared.read_bytes()).hexdigest()
        recipe = build_expression_recipe(self.master_sha)
        observation = {'synthetic_fixture': 'NOT_BLENDER_EVIDENCE'}
        report = root/'unit-prepared.json'
        report.write_text(json.dumps({'source_master_sha256': self.master_sha, 'prepared_sha256': prepared_sha,
            'policy': recipe['policy'], 'observation': observation,
            'visual_quality_approved': False, 'engine_import_verified': False}), encoding='utf-8', newline='\n')
        install_master_copy(self.store, prepared, prepared_sha, root)
        manifest = build_expression_manifest(source_intent(current), recipe, prepared_sha,
            sha256(report.read_bytes()).hexdigest(), canonical_digest(observation))
        self.expression_sha = publish_library(self.store, manifest, report)
        stage_unverified_master(self.store, prepared, authorized_source_root=root, expected_project=current,
            expected_revision=current.revision, proposed_expression=ExpressionState(self.expression_sha, tuple(DEFAULTS.items())))
        current = self.store.load()
        current = self.store.save(replace(current, facial_parameters=(('nose_width', .5),),
            expression=replace(current.expression, parameters=tuple((key, .5) for key in DEFAULTS)),
            revision=current.revision+1), expected_revision=current.revision)
        self.old_hand = None
        if hand:
            self.old_hand = self.library(self.store)
            self.select(self.store, self.old_hand, 'shorter', part_id='original-unit-hand')
        current = self.store.load(); publish_source_binding(self.store, current.project_id, self.reference)
        self.project = self.store.save(replace(current, animations=(self.clip_id,),
            revision=current.revision+1), expected_revision=current.revision)

    def library(self, store):
        current = store.load(); source_sha = current.master_blend.split('/')[-1][:-6]; assets = {}
        for variant in ('shorter', 'longer'):
            path = self.root/('unit-asset-'+variant+'.blend')
            path.write_bytes(b'BLENDER'+(source_sha+variant+'NOT_REAL_ASSET').encode()*30)
            sha = sha256(path.read_bytes()).hexdigest(); publish_asset(store, path, sha, path.parent)
            assets[variant] = {'sha256': sha, 'observation_sha256': 'e'*64}
        identity = publish_manifest(store, build_hand_manifest(build_hand_library_recipe(current, source_sha), assets))
        return load_hand_library(store, identity)

    def select(self, store, library, selection, *, part_id='private-unit-hand'):
        current = store.load()
        if selection == 'neutral':
            return stage_unverified_master(store, library.source_master,
                authorized_source_root=library.source_master.parent, expected_project=current,
                expected_revision=current.revision, proposed_parts=())
        path = self.root/'unit-selected.blend'
        path.write_bytes(b'BLENDER'+(library.sha256+selection+'NOT_REAL_SELECTION').encode()*30)
        sha = sha256(path.read_bytes()).hexdigest()
        publish_hand_receipt(store, build_hand_receipt(library.sha256, sha,
            library.manifest['recipe']['bindings']['master_sha256'], selection, 'f'*64))
        return stage_unverified_master(store, path, authorized_source_root=path.parent,
            expected_project=current, expected_revision=current.revision,
            proposed_parts=(PartInstance(part_id, hand_asset_id(library.sha256, selection), 'hand.L'),))

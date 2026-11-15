"""Synthetic plain-master storage fixture; not Blender geometry evidence."""
from dataclasses import replace
from fixtures.project_reference_contract import ReferenceFixture
from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.jobs.animation_reference_storage import publish_source_binding


class PlainReferenceMasterFixture(ReferenceFixture):
    library = ReferenceMasterFixture.library
    select = ReferenceMasterFixture.select
    saved_metadata_revision = ReferenceMasterFixture.saved_metadata_revision

    def __init__(self, root, *, hand=True, face=True):
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root)
        current = self.store.load()
        current = self.store.save(replace(current, schema_version=2 if face else 1,
            parameters=(('height', .5), ('muscle', .5), ('weight', .5)),
            facial_parameters=(('nose_width', .5),) if face else (), revision=current.revision+1),
            expected_revision=current.revision)
        self.old_hand = None
        if hand:
            self.old_hand = self.library(self.store)
            self.select(self.store, self.old_hand, 'shorter', part_id='original-plain-unit-hand')
        current = self.store.load()
        publish_source_binding(self.store, current.project_id, self.reference)
        self.project = self.store.save(replace(current, animations=(self.clip_id,),
            revision=current.revision+1), expected_revision=current.revision)

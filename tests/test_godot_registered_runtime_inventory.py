"""Streaming ownership inventory faults on nonshipping preparation bytes."""
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.godot_registered_retention_logic import RetentionFixture,digest
from ucc.core.errors import ProjectStorageError
from ucc.jobs import godot_registered_runtime_admission as admission
from ucc.jobs.target_action_context import Budget


class Inventory:
    def __init__(self,names):self.names=iter(names);self.requested=0;self.closed=False
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def __next__(self):
        self.requested+=1
        return SimpleNamespace(name=next(self.names))


class RegisteredPreparationInventoryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=RetentionFixture(Path(temp.name).resolve());self.event=Event()
        self.recipe=json.loads((self.f.work/"native_recipe.json").read_bytes())
        self.receipt=json.loads(self.f.preparation.production_receipt.read_bytes())
        paths=admission.preparation_paths(self.f.store,self.f.preparation)
        self.hashes={name:digest(path) for name,path in paths.items()}

    def watch(self):
        return admission.watch_preparation(self.f.preparation,self.recipe,self.receipt,self.hashes,Budget(self.event,60))

    def test_duplicate_flood_rejects_second_entry_before_hash_and_closes_iterator(self):
        inventory=Inventory(["candidate.blend"]*100000);real=admission.hash_file
        with patch("ucc.jobs.export_guards.os.scandir",return_value=inventory),patch.object(admission,"hash_file",wraps=real) as hashed:
            with self.assertRaisesRegex(ProjectStorageError,"duplicate"):self.watch()
        self.assertEqual(inventory.requested,2);self.assertTrue(inventory.closed)
        self.assertEqual(hashed.call_count,1)

    def test_first_foreign_entry_rejects_without_hash_or_draining_flood(self):
        inventory=Inventory(["FOREIGN.gd"]*100000)
        with patch("ucc.jobs.export_guards.os.scandir",return_value=inventory),patch.object(admission,"hash_file") as hashed:
            with self.assertRaises(ProjectStorageError):self.watch()
        self.assertEqual(inventory.requested,1);self.assertTrue(inventory.closed);hashed.assert_not_called()

    def test_cancel_after_first_file_stops_before_requesting_second_and_closes(self):
        inventory=Inventory(["candidate.blend","source.fbx"]);real=admission.hash_file
        def hashed(*args):
            result=real(*args);self.event.set();return result
        with patch("ucc.jobs.export_guards.os.scandir",return_value=inventory),patch.object(admission,"hash_file",side_effect=hashed):
            with self.assertRaises(ProjectStorageError):self.watch()
        self.assertEqual(inventory.requested,1);self.assertTrue(inventory.closed)

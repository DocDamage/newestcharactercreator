"""Metadata/Qt drafts only; fixtures and doubles never prove Blender integration."""
from dataclasses import replace
import os,unittest
from unittest.mock import patch
from ucc.core.commands import CharacterSession
from ucc.core.errors import ValidationError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
import test_material_master_desktop as desktop_tests
import test_desktop_qt as qt


class SkinMaterialAssignmentTests(unittest.TestCase):
    def setUp(self):desktop_tests.MaterialMasterHistoryTests.setUp(self)
    def test_first_assignment_requires_explicit_adopter_and_preserves_other_appearance(self):
        before=replace(self.before,appearance=(('other','retained'),));session=CharacterSession(before)
        with self.assertRaises(ValidationError):session.accept_saved_material_master(self.saved)
        session.accept_saved_material_master(self.saved,initial_assignment=True)
        undone=session.undo();self.assertEqual(undone.appearance,before.appearance)
        redone=session.redo();self.assertEqual(redone.appearance,self.saved.appearance)
        with self.assertRaises(ValidationError):CharacterSession(replace(before,animations=self.f.project.animations)).accept_saved_material_master(self.saved,initial_assignment=True)


@unittest.skipIf(qt.QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class SkinMaterialControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if qt.QApplication is None:raise RuntimeError(qt.IMPORT_ERROR)
        cls.app=qt.QApplication.instance() or qt.QApplication(['skin-material-controls'])

    def setUp(self):
        from ucc.desktop.skin_material_controls import SkinMaterialControls
        self.widget=SkinMaterialControls();self.addCleanup(self.widget.deleteLater)

    def test_no_silent_default_color_and_invalid_values_cannot_apply(self):
        self.widget.display('unit',None,eligible=True,clean=True)
        self.assertEqual(self.widget.color.text(),'');self.assertFalse(self.widget.apply.isEnabled())
        for text in ('white','#12345','#gggggg','#12345678'):
            self.widget.color.setText(text)
            with self.assertRaises(ValidationError):self.widget.draft_spec()
            self.assertFalse(self.widget.apply.isEnabled())
        self.widget.color.setText('#94603d');self.widget.roughness.setValue(.65)
        self.assertTrue(self.widget.apply.isEnabled());self.assertEqual(self.widget.draft_spec(),SkinMaterialSpec((148/255,96/255,61/255),.65))

    def test_loaded_nonquantized_parameters_stay_exact_without_edits(self):
        spec=SkinMaterialSpec((.581234567,.312345678,.198765432),.623456789)
        self.widget.display('unit',spec,eligible=True,clean=True)
        self.assertEqual(self.widget.draft_spec(),spec)
        self.widget.roughness.setValue(.7);self.assertEqual(self.widget.draft_spec().base_color_srgb,spec.base_color_srgb)
        self.widget.color.setText('#123456');self.assertEqual(self.widget.draft_spec().roughness,.7)

    def test_refresh_preserves_local_draft_until_saved_spec_or_project_changes(self):
        spec=SkinMaterialSpec((.5,.3,.2),.6);self.widget.display('unit',spec,eligible=True,clean=True)
        self.widget.color.setText('#123456');draft=self.widget.draft_spec()
        self.widget.display('unit',spec,eligible=True,clean=False);self.assertEqual(self.widget.draft_spec(),draft)
        self.assertFalse(self.widget.apply.isEnabled())
        self.widget.display('unit',draft,eligible=True,clean=True);self.assertEqual(self.widget.draft_spec(),draft)
        self.widget.display('other',None,eligible=True,clean=True);self.assertEqual(self.widget.color.text(),'')

    def test_apply_emits_explicit_immutable_spec_and_never_changes_project_metadata(self):
        self.widget.display('unit',None,eligible=True,clean=True);self.widget.color.setText('#123456')
        values=[];self.widget.apply_requested.connect(values.append);self.widget.apply.click()
        self.assertEqual(len(values),1);self.assertIsInstance(values[0],SkinMaterialSpec)

    def test_picker_cancel_preserves_draft_and_valid_choice_uses_explicit_rgb(self):
        from PySide6.QtGui import QColor
        self.widget.display('unit',None,eligible=True,clean=True)
        with patch('ucc.desktop.skin_material_controls.QColorDialog.getColor',return_value=QColor()):self.widget.choose.click()
        self.assertEqual(self.widget.color.text(),'');self.assertFalse(self.widget.apply.isEnabled())
        with patch('ucc.desktop.skin_material_controls.QColorDialog.getColor',return_value=QColor('#123456')):self.widget.choose.click()
        self.assertEqual(self.widget.color.text(),'#123456');self.assertTrue(self.widget.apply.isEnabled())

    def test_temporary_provenance_error_disables_apply_and_keeps_local_draft(self):
        spec=SkinMaterialSpec((.5,.3,.2),.6);self.widget.display('unit',spec,eligible=True,clean=True)
        self.widget.color.setText('#123456');draft=self.widget.draft_spec()
        self.widget.display('unit',None,eligible=False,clean=False,error='UNIT provenance unavailable')
        self.assertEqual(self.widget.draft_spec(),draft);self.assertFalse(self.widget.apply.isEnabled())
        self.widget.display('unit',spec,eligible=True,clean=True);self.assertEqual(self.widget.draft_spec(),draft)

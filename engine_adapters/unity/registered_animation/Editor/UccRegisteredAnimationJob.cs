using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ucc.UnityAdapter.Editor {
    [InitializeOnLoad]
    public static class UccRegisteredAnimationJob {
        const string Folder = "Assets/UCC/";
        const string Fbx = Folder + "animated_character.fbx";
        const string SkinAsset = Folder + "CharacterSkin.asset";
        const string Controller = Folder + "RegisteredLoop.controller";
        const string Scene = Folder + "AnimatedCharacter.unity";
        const string Character = "UCC_RegisteredAnimation";
        const string BindPolicy = "UCC_UNITY_REGISTERED_ANIMATION_BIND_V1";
        static string Project => Directory.GetParent(Application.dataPath).FullName;
        static string BindPath => Path.Combine(Project, "unity-animation-bind.json");
        static string Marker => Path.Combine(Project, "unity-animation-active.txt");

        [Serializable] sealed class Inputs {
            public int schema_version;
            public string policy, binding_sha256, master_sha256, fbx_sha256, weights_sha256;
        }

        [Serializable] sealed class Expect {
            public int schema_version;
            public string policy, bind_sha256;
        }

        [Serializable] sealed class Bone {
            public string name, parent;
            public float[] rest_world;
        }

        [Serializable] sealed class Bind {
            public int schema_version = 1;
            public string policy = BindPolicy;
            public string binding_sha256, master_sha256, fbx_sha256, native_mesh_sha256, clip_name;
            public int fps = UccRegisteredAnimatorSampler.FramesPerSecond;
            public int duration_seconds = (int)UccRegisteredAnimatorSampler.DurationSeconds, native_vertices;
            public int[] native_to_source;
            public string[] shape_names;
            public Bone[] bones;
        }

        static UccRegisteredAnimationJob() {
            EditorApplication.playModeStateChanged += AttachObserver;
            EditorApplication.update += CheckTerminal;
        }

        static void Require(bool condition, string message) {
            if (!condition) throw new InvalidDataException(message);
        }

        static bool IsDigest(string value) => value != null && value.Length == 64
            && value.All(c => c >= '0' && c <= '9' || c >= 'a' && c <= 'f');

        static byte[] ReadBound(string path, int limit, string digest = null) {
            var file = new FileInfo(path);
            Require(file.Exists && file.Length > 0 && file.Length <= limit
                && (file.Attributes & FileAttributes.ReparsePoint) == 0, "Unity animation input is missing, redirected or oversized");
            byte[] raw;
            using (var stream = File.OpenRead(path)) {
                Require(stream.Length == file.Length, "Unity animation input length changed");
                using (var reader = new BinaryReader(stream)) {
                    raw = reader.ReadBytes((int)file.Length);
                    Require(raw.Length == file.Length && reader.BaseStream.ReadByte() == -1, "Unity animation input grew during admission");
                }
            }
            Require(digest == null || UccNativeMeshIdentity.Hash(raw) == digest, "Unity animation staged input differs from its bound SHA");
            return raw;
        }

        static Inputs ReadInputs() {
            Require(Application.unityVersion == "6000.4.5f1", "Use the admitted Unity 6000.4.5f1 editor");
            var raw = ReadBound(Path.Combine(Project, "unity-animation-inputs.json"), 64 * 1024);
            var input = JsonUtility.FromJson<Inputs>(System.Text.Encoding.UTF8.GetString(raw));
            Require(input != null && input.schema_version == 1 && input.policy == "UCC_UNITY_REGISTERED_ANIMATION_IMPORT_V1"
                && new[] { input.binding_sha256, input.master_sha256, input.fbx_sha256, input.weights_sha256 }.All(IsDigest),
                "Unity animation input envelope differs from the registered profile");
            ReadBound(Path.Combine(Project, Fbx), 256 * 1024 * 1024, input.fbx_sha256);
            ReadBound(Path.Combine(Project, Folder + "source_weights.json"), 8 * 1024 * 1024, input.weights_sha256);
            return input;
        }

        // The same native importer controls are exercised on a nonshipping two-bone fixture.
        public static AnimationClip ConfigureNativeClip(string assetPath) {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            Require(importer != null, "Actual registered FBX importer missing");
            importer.animationType = ModelImporterAnimationType.Generic;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.importAnimation = true;
            importer.animationCompression = ModelImporterAnimationCompression.Off;
            importer.importBlendShapes = true;
            importer.meshCompression = ModelImporterMeshCompression.Off;
            importer.weldVertices = false;
            importer.isReadable = true;
            importer.importNormals = ModelImporterNormals.Import;
            importer.importBlendShapeNormals = ModelImporterNormals.Import;
            importer.materialImportMode = ModelImporterMaterialImportMode.None;
            importer.skinWeights = ModelImporterSkinWeights.Custom;
            importer.maxBonesPerVertex = 8;
            importer.minBoneWeight = .001f;
            importer.optimizeBones = false;
            importer.optimizeGameObjects = false;
            importer.preserveHierarchy = true;
            importer.bakeAxisConversion = true;
            importer.useFileScale = true;
            importer.globalScale = 1f;
            importer.SaveAndReimport();
            var definitions = importer.defaultClipAnimations;
            Require(definitions.Length == 1, "Registered animated FBX requires exactly one native take");
            definitions[0].loopTime = true;
            definitions[0].loopPose = false;
            importer.clipAnimations = definitions;
            importer.SaveAndReimport();
            return ReadNativeClip(assetPath);
        }

        static AnimationClip ReadNativeClip(string assetPath) {
            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            Require(importer != null && importer.importAnimation && importer.animationType == ModelImporterAnimationType.Generic
                && importer.animationCompression == ModelImporterAnimationCompression.Off
                && importer.clipAnimations.Length == 1 && importer.clipAnimations[0].loopTime
                && !importer.clipAnimations[0].loopPose, "Saved native Generic animation import settings changed");
            var clips = AssetDatabase.LoadAllAssetsAtPath(assetPath).OfType<AnimationClip>()
                .Where(clip => !clip.name.StartsWith("__preview__", StringComparison.Ordinal)).ToArray();
            Require(clips.Length == 1, "Registered animated FBX must expose exactly one native clip");
            var result = clips[0];
            Require(!result.legacy && result.isLooping && Math.Abs(result.length-UccRegisteredAnimatorSampler.DurationSeconds) < .00005f
                && Math.Abs(result.frameRate-UccRegisteredAnimatorSampler.FramesPerSecond) < .00005f
                && AnimationUtility.GetCurveBindings(result).Any(binding => binding.type == typeof(Transform) && binding.path.Length > 0),
                "Native registered clip is missing skeletal tracks or its 30 Hz ten-second loop");
            return result;
        }

        public static Animator RequireAnimator(GameObject root) {
            var animators = root.GetComponentsInChildren<Animator>(true);
            Require(animators.Length == 1 && animators[0].avatar != null && animators[0].avatar.isValid && !animators[0].avatar.isHuman,
                "Registered scene requires exactly one valid native Generic Animator");
            return animators[0];
        }

        static void SetSkinQuality() {
            QualitySettings.skinWeights = SkinWeights.Unlimited;
            var quality = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/QualitySettings.asset")[0]);
            var levels = quality.FindProperty("m_QualitySettings");
            Require(levels != null && levels.isArray && levels.arraySize > 0, "Missing native Unity quality settings");
            for (int index = 0; index < levels.arraySize; index++) {
                var limit = levels.GetArrayElementAtIndex(index).FindPropertyRelative("skinWeights");
                Require(limit != null, "Missing native skin weight setting");
                limit.intValue = 255;
            }
            quality.ApplyModifiedPropertiesWithoutUndo();
        }

        static Bone[] BindBones(SkinnedMeshRenderer skin) {
            var bones = skin.bones;
            var names = bones.Select(bone => bone.name).ToArray();
            Require(names.Length == 163 && names.Distinct(StringComparer.Ordinal).Count() == names.Length,
                "Native registered bone names are incomplete or ambiguous");
            var known = new System.Collections.Generic.HashSet<string>(names, StringComparer.Ordinal);
            var matrices = skin.sharedMesh.bindposes;
            return bones.Select((bone, index) => new Bone {
                name = bone.name, parent = bone.parent != null && known.Contains(bone.parent.name) ? bone.parent.name : "",
                rest_world = UccRegisteredAnimatorSampler.RowMajor(skin.localToWorldMatrix * matrices[index].inverse),
            }).ToArray();
        }

        static string[] ShapeNames(SkinnedMeshRenderer skin) {
            var mesh = skin.sharedMesh;
            var names = Enumerable.Range(0, mesh.blendShapeCount).Select(mesh.GetBlendShapeName).ToArray();
            Require(names.Length == 12 && names.Distinct(StringComparer.Ordinal).Count() == names.Length
                && names.All(name => name.StartsWith("UCC_EXPR_V1_", StringComparison.Ordinal)),
                "Native registered expression identities differ from the source profile");
            return names;
        }

        static void ConfigurePreview(SkinnedMeshRenderer skin) {
            var bounds = skin.bounds;
            Require(bounds.size.y > .1f && bounds.size.y < 4f, "Registered preview bounds are outside the metre profile");
            var camera = new GameObject("UCC Preview Camera").AddComponent<Camera>();
            camera.renderingPath = RenderingPath.Forward;
            camera.orthographic = true;
            camera.orthographicSize = bounds.size.y * .65f;
            camera.transform.position = bounds.center + new Vector3(0f, 0f, bounds.size.y * 3f);
            camera.transform.LookAt(bounds.center);
            var light = new GameObject("UCC Preview Light").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(30f, 155f, 0f);
        }

        public static void Stage() {
            try {
                var inputs = ReadInputs();
                Require(!new[] {Scene, Controller, SkinAsset, BindPath}.Any(File.Exists), "Use an unpopulated registered import workspace");
                var clip = ConfigureNativeClip(Fbx);
                var source = AssetDatabase.LoadAssetAtPath<GameObject>(Fbx);
                Require(source != null, "Actual imported registered FBX hierarchy missing");
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var character = (GameObject)PrefabUtility.InstantiatePrefab(source);
                character.name = Character;
                var animator = RequireAnimator(character);
                var skin = character.GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
                character.transform.rotation = Quaternion.AngleAxis(180f, Vector3.up) * character.transform.rotation;
                var mapping = UccSourceWeights.Apply(skin, Path.Combine(Project, Folder + "source_weights.json"),
                    inputs.weights_sha256, inputs.master_sha256, inputs.binding_sha256, SkinAsset);
                skin.updateWhenOffscreen = true;
                skin.quality = SkinQuality.Auto;
                animator.runtimeAnimatorController = AnimatorController.CreateAnimatorControllerAtPathWithClip(Controller, clip);
                animator.applyRootMotion = false;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                var fingerprint = UccNativeMeshIdentity.Compute(skin);
                SetSkinQuality();
                ConfigurePreview(skin);
                Require(EditorSceneManager.SaveScene(scene, Scene), "Registered character scene could not be saved");
                AssetDatabase.SaveAssets();
                var bind = new Bind {
                    binding_sha256 = inputs.binding_sha256, master_sha256 = inputs.master_sha256, fbx_sha256 = inputs.fbx_sha256,
                    native_mesh_sha256 = fingerprint, clip_name = clip.name, native_vertices = skin.sharedMesh.vertexCount,
                    native_to_source = mapping, bones = BindBones(skin),
                    shape_names = ShapeNames(skin),
                };
                using (var stream = new StreamWriter(new FileStream(BindPath, FileMode.CreateNew))) stream.Write(JsonUtility.ToJson(bind));
                EditorApplication.Exit(0);
            } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
        }

        public static void Verify() {
            try {
                var inputs = ReadInputs();
                Require(!new[] {Marker, UccRegisteredAnimationObserver.Result, UccRegisteredAnimationObserver.Terminal,
                    UccRegisteredAnimationObserver.Bones, UccRegisteredAnimationObserver.Skin}.Any(File.Exists),
                    "Use a fresh relocated animation verification workspace");
                var expectation = JsonUtility.FromJson<Expect>(System.Text.Encoding.UTF8.GetString(
                    ReadBound(Path.Combine(Project, "unity-animation-expect.json"), 64 * 1024)));
                Require(expectation != null && expectation.schema_version == 1 && IsDigest(expectation.bind_sha256)
                    && expectation.policy == "UCC_UNITY_REGISTERED_ANIMATION_VERIFY_V1", "Expected Unity binding pin is missing");
                var bind = JsonUtility.FromJson<Bind>(System.Text.Encoding.UTF8.GetString(ReadBound(BindPath, 4 * 1024 * 1024, expectation.bind_sha256)));
                var clip = ReadNativeClip(Fbx);
                var scene = EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
                var character = scene.GetRootGameObjects().Single(root => root.name == Character);
                var animator = RequireAnimator(character);
                var skin = character.GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
                Require(bind != null && bind.schema_version == 1 && bind.policy == BindPolicy && bind.binding_sha256 == inputs.binding_sha256
                    && bind.master_sha256 == inputs.master_sha256 && bind.fbx_sha256 == inputs.fbx_sha256 && bind.clip_name == clip.name
                    && bind.fps == 30 && bind.duration_seconds == 10 && bind.native_vertices == skin.sharedMesh.vertexCount
                    && bind.native_mesh_sha256 == UccNativeMeshIdentity.Compute(skin)
                    && bind.shape_names != null && bind.shape_names.SequenceEqual(ShapeNames(skin))
                    && AssetDatabase.GetAssetPath(skin.sharedMesh) == SkinAsset && bind.native_to_source?.Length == bind.native_vertices
                    && bind.native_to_source.All(index => index >= 0 && index < 13380) && bind.native_to_source.Distinct().Count() == 13380,
                    "Reopened registered mesh, correspondence or clip identity differs");
                var bones = BindBones(skin);
                Require(bind.bones?.Length == bones.Length && bones.Zip(bind.bones, (fresh, staged) => fresh.name == staged.name
                    && fresh.parent == staged.parent && fresh.rest_world.SequenceEqual(staged.rest_world)).All(valid => valid),
                    "Reopened native bone rest binding differs");
                Require(animator.enabled && !animator.applyRootMotion && animator.cullingMode == AnimatorCullingMode.AlwaysAnimate
                    && animator.runtimeAnimatorController != null && AssetDatabase.GetAssetPath(animator.runtimeAnimatorController) == Controller
                    && animator.runtimeAnimatorController.animationClips.SequenceEqual(new[] { clip }),
                    "Reopened scene does not bind its exact native Animator Controller");
                using (var stream = new StreamWriter(new FileStream(Marker, FileMode.CreateNew)))
                    stream.Write(expectation.bind_sha256 + "\n" + inputs.binding_sha256);
                EditorApplication.isPlaying = true;
            } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
        }

        static void AttachObserver(PlayModeStateChange state) {
            if (state != PlayModeStateChange.EnteredPlayMode || !File.Exists(Marker)) return;
            try {
                var pins = File.ReadAllLines(Marker);
                Require(pins.Length == 2 && pins.All(IsDigest), "Registered observation marker changed");
                var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
                scene.GetRootGameObjects().Single(root => root.name == Character).AddComponent<UccRegisteredAnimationObserver>()
                    .Bind(pins[0], pins[1]);
            } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
        }

        static void CheckTerminal() {
            if (File.Exists(Marker) && File.Exists(UccRegisteredAnimationObserver.Terminal)) {
                bool valid = Int32.TryParse(File.ReadAllText(UccRegisteredAnimationObserver.Terminal), out int code);
                EditorApplication.Exit(valid && code == 0 ? 0 : 2);
            }
        }
    }
}

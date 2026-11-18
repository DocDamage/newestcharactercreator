using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ucc.UnityAdapter.Editor {
    [InitializeOnLoad]
    public static class UccRegisteredCorrectionVerify {
        const string Scene = "Assets/UCC/AnimatedCharacter.unity";
        static string Project => Directory.GetParent(Application.dataPath).FullName;
        static string Marker => Path.Combine(Project, "unity-correction-active.txt");

        [Serializable] sealed class Expectation {
            public int schema_version;
            public string policy, binding_sha256, native_mesh_sha256, topology_sha256, scene_sha256;
        }

        static UccRegisteredCorrectionVerify() {
            EditorApplication.playModeStateChanged += Attach;
            EditorApplication.update += ReadTerminal;
        }

        static void Require(bool condition, string error) {
            if (!condition) throw new InvalidDataException(error);
        }

        static bool Digest(string value) => value != null && value.Length == 64
            && value.All(character => character >= '0' && character <= '9' || character >= 'a' && character <= 'f');

        static byte[] ReadBound(string location, int limit) {
            var file = new FileInfo(location);
            Require(file.Exists && file.Length > 0 && file.Length <= limit && (file.Attributes & FileAttributes.ReparsePoint) == 0,
                "Missing or redirected Unity correction verification input");
            using (var stream = File.OpenRead(location))
                using (var reader = new BinaryReader(stream)) {
                    long length = stream.Length;
                    Require(length == file.Length && length <= limit, "Unity correction input length changed");
                    byte[] bytes = reader.ReadBytes((int)length);
                    Require(bytes.Length == length && stream.ReadByte() == -1, "Unity correction input changed during reading");
                    return bytes;
                }
        }

        public static void Run() {
            try {
                Require(Application.unityVersion == "6000.4.5f1" && !Application.isPlaying,
                    "Registered corrected playback requires the admitted editor version");
                Require(!new[] {Marker, UccRegisteredCorrectionObserver.Terminal, UccRegisteredCorrectionObserver.Result,
                    UccRegisteredCorrectionObserver.Rendered}.Any(File.Exists), "Correction verification output already exists");
                var raw = ReadBound(Path.Combine(Project, "unity-correction-expect.json"), 65536);
                var plan = JsonUtility.FromJson<Expectation>(new UTF8Encoding(false, true).GetString(raw));
                Require(plan != null && plan.schema_version == 1 && plan.policy == "UCC_UNITY_REGISTERED_CORRECTION_VERIFY_V1",
                    "Unsupported correction verification profile");
                string[] pins = {plan.binding_sha256, plan.native_mesh_sha256, plan.topology_sha256, plan.scene_sha256};
                Require(pins.All(Digest) && UccNativeMeshIdentity.Hash(ReadBound(Path.Combine(Project, Scene), 16*1024*1024)) == plan.scene_sha256,
                    "Corrected preview scene differs from its selected bytes");
                var scene = EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
                var character = scene.GetRootGameObjects().Single(root => root.name == "UCC_RegisteredAnimation");
                var skin = character.GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
                var hook = skin.GetComponent<UccNativeNormals>();
                Require(hook != null && hook.enabled && UccNativeMeshIdentity.Compute(skin) == plan.native_mesh_sha256,
                    "Saved corrected scene mesh or active adapter differs");
                var fields = new SerializedObject(hook);
                Require(fields.FindProperty("requiresPositionCorrection").boolValue
                    && fields.FindProperty("sourceDataSha256").stringValue == plan.topology_sha256
                    && AssetDatabase.GetAssetPath(fields.FindProperty("sourceData").objectReferenceValue) == "Assets/UCC/source_quads.json"
                    && fields.FindProperty("positionCorrectionBinding").objectReferenceValue is UccRegisteredNormalsCorrectionBinding binding
                    && AssetDatabase.GetAssetPath(binding) == "Assets/UCC/RegisteredCorrection.asset",
                    "Saved scene lacks the SHA-bound registered correction and original quad binding");
                using (var writer = new StreamWriter(new FileStream(Marker, FileMode.CreateNew)))
                    writer.Write(String.Join("\n", pins));
                EditorApplication.isPlaying = true;
            } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
        }

        static void Attach(PlayModeStateChange state) {
            if (state != PlayModeStateChange.EnteredPlayMode || !File.Exists(Marker)) return;
            try {
                var pins = new UTF8Encoding(false, true).GetString(ReadBound(Marker, 1024)).Split('\n');
                Require(pins.Length == 4 && pins.All(Digest), "Corrected animation local marker changed");
                var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
                scene.GetRootGameObjects().Single(root => root.name == "UCC_RegisteredAnimation")
                    .AddComponent<UccRegisteredCorrectionObserver>().Bind(pins);
            } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
        }

        static void ReadTerminal() {
            if (File.Exists(Marker) && File.Exists(UccRegisteredCorrectionObserver.Terminal)) {
                try {
                    bool passed = new UTF8Encoding(false, true).GetString(ReadBound(UccRegisteredCorrectionObserver.Terminal, 16)) == "0";
                    EditorApplication.Exit(passed ? 0 : 2);
                } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
            }
        }
    }
}

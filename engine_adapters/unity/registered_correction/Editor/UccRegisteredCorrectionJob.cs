using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ucc.UnityAdapter.Editor {
    public static class UccRegisteredCorrectionJob {
        const string Folder = "Assets/UCC/";
        const string Scene = Folder + "AnimatedCharacter.unity";
        const string Binding = Folder + "RegisteredCorrection.asset";
        const string MaterialPath = Folder + "NeutralPreview.mat";
        static readonly string[] Names = { "neighbor_ranges.u32", "neighbors.u32", "corners.u32",
            "offsets_vec4.f32", "corner_ranges.u32", "corner_indices.u32" };

        [Serializable] sealed class Operand {
            public string name, sha256;
        }

        [Serializable] sealed class Plan {
            public int schema_version;
            public string policy, native_mesh_sha256, topology_sha256;
            public Operand[] operands;
        }

        static void Require(bool condition, string reason) {
            if (!condition) throw new InvalidDataException(reason);
        }

        static T Asset<T>(string name) where T : UnityEngine.Object {
            var asset = AssetDatabase.LoadAssetAtPath<T>(Folder + name);
            if (asset == null) throw new InvalidDataException("Missing source-bound Unity asset " + name);
            return asset;
        }

        public static void Attach() {
            try {
                Require(Application.unityVersion == "6000.4.5f1" && !Application.isPlaying,
                    "Corrective attachment needs the pinned Unity editor outside Play Mode");
                Require(!File.Exists(Binding) && !File.Exists(MaterialPath), "Correction workspace already contains a saved binding");
                string project = Directory.GetParent(Application.dataPath).FullName;
                var planPath = Path.Combine(project, "unity-animation-correction.json");
                Require(File.Exists(planPath) && new FileInfo(planPath).Length <= 65536,
                    "Missing or oversized local Unity correction plan");
                var plan = JsonUtility.FromJson<Plan>(File.ReadAllText(planPath));
                Require(plan != null && plan.schema_version == 1 && plan.policy == "UCC_UNITY_ANIMATED_CORRECTION_ATTACH_V1"
                    && plan.operands != null && plan.operands.Length == Names.Length
                    && plan.operands.Select(row => row?.name).SequenceEqual(Names),
                    "Unity corrective plan has unexpected operand identities");

                var scene = EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
                var character = scene.GetRootGameObjects().Single(root => root.name == "UCC_RegisteredAnimation");
                var skin = character.GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
                Require(skin.GetComponent<UccNativeNormals>() == null && UccNativeMeshIdentity.Compute(skin) == plan.native_mesh_sha256,
                    "Saved Unity skin changed before corrective attachment");
                var quadData = Asset<TextAsset>("source_quads.json");
                UccQuadSourceData.Read(quadData, plan.topology_sha256, skin);
                var resources = plan.operands.Select(row => new UccCorrectionTopologyAsset {
                    name = row.name, sha256 = row.sha256, bytes = Asset<TextAsset>("CorrectionData/" + row.name + ".bytes"),
                }).ToArray();
                foreach (var row in resources)
                    Require(row.sha256 == UccNativeMeshIdentity.Hash(row.bytes.bytes), "Unity corrective operand SHA changed");

                var corrections = ScriptableObject.CreateInstance<UccRegisteredNormalsCorrectionBinding>();
                corrections.ConfigureForExport(Asset<ComputeShader>("UccRegisteredCorrection.compute"), resources);
                AssetDatabase.CreateAsset(corrections, Binding);
                var shader = Shader.Find("Standard");
                Require(shader != null, "Built-in Standard preview shader is unavailable");
                var neutral = new Material(shader) { name = "UCC neutral preview" };
                neutral.SetColor("_Color", new Color(.52f, .56f, .61f, 1f));
                neutral.SetFloat("_Glossiness", .25f);
                AssetDatabase.CreateAsset(neutral, MaterialPath);
                skin.sharedMaterials = new[] { neutral };
                PlayerSettings.colorSpace = ColorSpace.Linear;
                var adapter = skin.gameObject.AddComponent<UccNativeNormals>();
                adapter.ConfigureForExport(quadData, plan.topology_sha256, Asset<ComputeShader>("UccRegisteredQuadNormals.compute"),
                    Asset<Shader>("UccNativeSkinWarmup.shader"), corrections);
                Require(EditorSceneManager.SaveScene(scene), "Could not save the corrected preview scene");
                AssetDatabase.SaveAssets();
                EditorApplication.Exit(0);
            } catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(2); }
        }
    }
}

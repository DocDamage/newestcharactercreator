#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEngine;

namespace Ucc.UnityAdapter {
    // Transient editor verification only. The saved Animator plays without this observer.
    public sealed class UccRegisteredAnimationObserver : MonoBehaviour {
        static string Project => Directory.GetParent(Application.dataPath).FullName;
        public static string Result => Path.Combine(Project, "unity-animation-observation.json");
        public static string Terminal => Path.Combine(Project, "unity-animation-terminal.txt");
        public static string Bones => Path.Combine(Project, "unity-animation-bones.f32");
        public static string Skin => Path.Combine(Project, "unity-animation-raw-skin.f32");

        [Serializable] sealed class Evidence {
            public int schema_version = 1;
            public string policy = "UCC_UNITY_REGISTERED_ANIMATION_OBSERVATION_V1";
            public string bind_sha256, binding_sha256, clip_name, unity;
            public bool normal_animation_advanced = true, normal_loop_wrapped = true;
            public int fixed_clock_samples = UccRegisteredAnimatorSampler.Samples, bone_count, native_vertices;
            public string bones_sha256, raw_skin_sha256;
            public bool corrective_runtime_verified = false, visual_quality_approved = false;
        }

        Animator animator;
        SkinnedMeshRenderer skin;
        Transform[] bones;
        Mesh sampled;
        AnimationClip clip;
        string bindSha, bindingSha;
        int elapsedFrames, savedCaptureRate, observedState;
        float previous = -1f;
        bool observedStart, observedInterior, completed, changedCaptureRate;

        public void Bind(string bindPin, string bindingPin) {
            if (bindSha != null || bindPin == null || bindingPin == null)
                throw new InvalidDataException("Registered observation already bound or incomplete");
            bindSha = bindPin;
            bindingSha = bindingPin;
        }

        static void Require(bool condition, string reason) {
            if (!condition) throw new InvalidDataException(reason);
        }

        void Start() {
            try {
                Require(bindSha != null && bindingSha != null, "Unbound registered playback observer");
                animator = GetComponentsInChildren<Animator>(true).Single();
                skin = GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
                bones = skin.bones;
                clip = animator.runtimeAnimatorController.animationClips.Single();
                Require(animator.enabled && !animator.applyRootMotion && clip.isLooping && bones.Length == 163
                    && skin.sharedMesh.isReadable && QualitySettings.skinWeights == SkinWeights.Unlimited,
                    "Reopened scene lost its registered native playback or weight profile");
                sampled = new Mesh();
                savedCaptureRate = Time.captureFramerate;
                Time.captureFramerate = 60;
                changedCaptureRate = true;
            } catch (Exception error) { Complete(2, error); }
        }

        void LateUpdate() {
            if (completed) return;
            try {
                Require(++elapsedFrames < 1000, "Timed out waiting for ordinary registered Unity autoplay and wrap");
                if (!animator.isInitialized) return;
                var state = animator.GetCurrentAnimatorStateInfo(0);
                float clock = state.normalizedTime;
                Require(UccRegisteredAnimatorSampler.Finite(clock) && clock >= previous && state.loop,
                    "Ordinary native animation clock stopped looping or moved backwards");
                if (!observedStart && clock > 0f && clock < .10f) {
                    observedStart = true;
                    observedState = state.fullPathHash;
                }
                if (observedStart) Require(state.fullPathHash == observedState, "Ordinary playback changed the registered native state");
                if (clock > .25f && clock < .75f) observedInterior = true;
                if (clock >= 1f) {
                    Require(observedStart && observedInterior && previous >= .98f && previous < 1f && clock < 1.05f,
                        "Ordinary native Animation did not advance through a complete wrap");
                    Capture(state.fullPathHash);
                    Complete(0, null);
                }
                previous = clock;
            } catch (Exception error) { Complete(2, error); }
        }

        static string HashFile(string path) {
            using (var stream = File.OpenRead(path))
                using (var hash = SHA256.Create())
                    return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        void Capture(int stateHash) {
            int vertices = skin.sharedMesh.vertexCount;
            var raw = new List<Vector3>(vertices);
            using (var matrices = new BinaryWriter(new FileStream(Bones, FileMode.CreateNew)))
                using (var geometry = new BinaryWriter(new FileStream(Skin, FileMode.CreateNew))) {
                    UccRegisteredAnimatorSampler.VisitFrames(animator, stateHash, _ => {
                        foreach (var bone in bones)
                            foreach (float scalar in UccRegisteredAnimatorSampler.RowMajor(bone.localToWorldMatrix))
                                matrices.Write(scalar);
                        skin.BakeMesh(sampled, false);
                        sampled.GetVertices(raw);
                        Require(raw.Count == vertices, "Native CPU skin readback lost vertices");
                        var world = skin.localToWorldMatrix;
                        foreach (var point in raw) {
                            var position = world.MultiplyPoint3x4(point);
                            Require(UccRegisteredAnimatorSampler.Finite(position.x) && UccRegisteredAnimatorSampler.Finite(position.y)
                                && UccRegisteredAnimatorSampler.Finite(position.z), "Nonfinite native CPU-skinned vertex");
                            geometry.Write(position.x);
                            geometry.Write(position.y);
                            geometry.Write(position.z);
                        }
                    });
                }
            Require(new FileInfo(Bones).Length == (long)UccRegisteredAnimatorSampler.Samples * bones.Length * 16 * sizeof(float)
                && new FileInfo(Skin).Length == (long)UccRegisteredAnimatorSampler.Samples * vertices * 3 * sizeof(float),
                "Incomplete native Animator readback streams");
            var result = new Evidence {
                bind_sha256 = bindSha, binding_sha256 = bindingSha, clip_name = clip.name, unity = Application.unityVersion,
                bone_count = bones.Length, native_vertices = vertices,
                bones_sha256 = HashFile(Bones), raw_skin_sha256 = HashFile(Skin),
            };
            using (var writer = new StreamWriter(new FileStream(Result, FileMode.CreateNew))) writer.Write(JsonUtility.ToJson(result));
        }

        void Complete(int code, Exception error) {
            completed = true;
            if (error != null) Debug.LogException(error);
            string pending = Terminal + ".pending";
            using (var writer = new StreamWriter(new FileStream(pending, FileMode.CreateNew))) writer.Write(code);
            File.Move(pending, Terminal);
        }

        void OnDestroy() {
            if (changedCaptureRate) Time.captureFramerate = savedCaptureRate;
            if (sampled != null) Destroy(sampled);
        }
    }
}
#endif

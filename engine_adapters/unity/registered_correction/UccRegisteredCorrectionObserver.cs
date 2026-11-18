#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ucc.UnityAdapter {
    // Verification-only observer. No expected positions or normals enter this process.
    public sealed class UccRegisteredCorrectionObserver : MonoBehaviour {
        const int Size = 384;
        const int NativeStride = 40;
        const int RecordStride = 24;
        const int LightProbeSample = 75;
        const int OppositeSample = 225;
        static string Project => Directory.GetParent(Application.dataPath).FullName;
        public static string Result => Path.Combine(Project, "unity-correction-observation.json");
        public static string Terminal => Path.Combine(Project, "unity-correction-terminal.txt");
        public static string Rendered => Path.Combine(Project, "unity-correction-rendered.f32");

        [Serializable] sealed class Row {
            public int sample, engine_frame, camera_id, completed_frame, completed_camera;
            public long offset;
        }

        [Serializable] sealed class Evidence {
            public int schema_version = 1;
            public string policy = "UCC_UNITY_REGISTERED_CORRECTION_OBSERVATION_V1";
            public string binding_sha256, native_mesh_sha256, topology_sha256, scene_sha256, unity, graphics;
            public bool normal_animator_wrap = true, lit_raster_changed = true, motion_raster_changed = true;
            public int native_vertices;
            public string corrected_sha256;
            public Row[] rows;
        }

        readonly List<Row> rows = new List<Row>();
        string[] pins;
        Animator animator;
        SkinnedMeshRenderer skin;
        UccNativeNormals hook;
        Camera view;
        Light keyLight;
        RenderTexture previousTarget, target;
        Texture2D pixels;
        BinaryWriter output;
        Color32[] litReference, motionReference;
        string litPoseBufferSha256;
        Quaternion lightOrientation;
        int savedCaptureRate, observedState, engineTicks, requestedFrame = -1, requestedSample;
        int normalWrapFrame = -1;
        int? terminalCode;
        float previousClock = -1f;
        bool observedStart, observedInterior, wrapped, wrapDrawn, complete, changedCaptureRate, litProbe;

        public void Bind(string[] identities) {
            Require(pins == null && identities?.Length == 4, "Corrected playback observer requires four exact local pins");
            pins = (string[])identities.Clone();
        }

        static void Require(bool condition, string error) {
            if (!condition) throw new InvalidDataException(error);
        }

        void Start() {
            try {
                Require(pins != null && Application.unityVersion == "6000.4.5f1"
                    && SystemInfo.graphicsDeviceType == GraphicsDeviceType.Direct3D11 && SystemInfo.supportsComputeShaders,
                    "Corrected playback requires the admitted D3D11 Unity editor");
                animator = GetComponentsInChildren<Animator>(true).Single();
                skin = GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
                hook = skin.GetComponent<UccNativeNormals>();
                var clip = animator.runtimeAnimatorController.animationClips.Single();
                Require(hook != null && hook.PositionCorrectionActive && hook.LastError == "" && animator.enabled
                    && !animator.applyRootMotion && clip.isLooping && Math.Abs(clip.length - 10f) < .00005f
                    && Math.Abs(clip.frameRate - 30f) < .00005f && QualitySettings.activeColorSpace == ColorSpace.Linear,
                    "Reopened scene did not initialize its admitted native Animator and correction");
                var roots = gameObject.scene.GetRootGameObjects();
                view = roots.Single(root => root.name == "UCC Preview Camera").GetComponent<Camera>();
                keyLight = roots.Single(root => root.name == "UCC Preview Light").GetComponent<Light>();
                Require(view != null && view.isActiveAndEnabled && view.renderingPath == RenderingPath.Forward
                    && keyLight != null && keyLight.isActiveAndEnabled
                    && keyLight.type == LightType.Directional, "Reopened scene lacks the saved active camera or directional light");
                lightOrientation = keyLight.transform.rotation;
                previousTarget = view.targetTexture;
                view.clearFlags = CameraClearFlags.SolidColor;
                view.backgroundColor = new Color(.025f, .025f, .025f, 0f);
                view.allowHDR = false;
                view.allowMSAA = false;
                target = new RenderTexture(Size, Size, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
                Require(target.Create(), "Could not create the private lit observation target");
                view.targetTexture = target;
                pixels = new Texture2D(Size, Size, TextureFormat.RGBA32, false);
                savedCaptureRate = Time.captureFramerate;
                Time.captureFramerate = 60;
                changedCaptureRate = true;
                Camera.onPostRender += Capture;
            } catch (Exception error) { Finish(2, error); }
        }

        void LateUpdate() {
            if (complete) {
                if (terminalCode.HasValue) FinishAfterRender();
                return;
            }
            try {
                Require(++engineTicks < 1800 && hook.PositionCorrectionActive && hook.LastError == "",
                    "Corrected native playback did not remain active within the frame budget");
                if (!wrapped) {
                    if (!animator.isInitialized) return;
                    var state = animator.GetCurrentAnimatorStateInfo(0);
                    float clock = state.normalizedTime;
                    Require(state.loop && UccRegisteredAnimatorSampler.Finite(clock) && clock >= previousClock,
                        "Ordinary native corrected playback stopped advancing its loop");
                    if (!observedStart && clock > 0f && clock < .10f) {
                        observedStart = true;
                        observedState = state.fullPathHash;
                    }
                    if (observedStart) Require(state.fullPathHash == observedState, "Ordinary Animator unexpectedly changed states");
                    if (clock > .25f && clock < .75f) observedInterior = true;
                    if (clock >= 1f) {
                        Require(observedStart && observedInterior && previousClock >= .98f && previousClock < 1f && clock < 1.05f
                            && hook.CompletedFrames > 2, "Normal Animator playback did not complete a drawn wrap");
                        wrapped = true;
                        normalWrapFrame = Time.frameCount;
                    }
                    previousClock = clock;
                    return;
                }
                Require(wrapDrawn, "Normal Animator wrap was not drawn by the saved camera");
                Require(requestedFrame < 0, "The saved camera did not draw the prior requested native sample");
                litProbe = rows.Count == UccRegisteredAnimatorSampler.Samples;
                requestedSample = litProbe ? LightProbeSample : rows.Count;
                if (litProbe) keyLight.transform.rotation = Quaternion.Euler(-20f, -135f, 0f);
                float phase = requestedSample / (float)UccRegisteredAnimatorSampler.Samples;
                animator.Play(observedState, 0, phase);
                animator.Update(0f);
                requestedFrame = Time.frameCount;
            } catch (Exception error) { Finish(2, error); }
        }

        void Capture(Camera renderedCamera) {
            if (complete || renderedCamera != view) return;
            try {
                int cameraId = view.GetInstanceID();
                if (normalWrapFrame == Time.frameCount && !wrapDrawn) {
                    Require(hook.PositionCorrectionActive && hook.LastError == "" && hook.CompletedFrame == normalWrapFrame
                        && hook.CompletedCamera == cameraId, "Normal wrap did not belong to the saved current-frame draw");
                    wrapDrawn = true;
                    output = new BinaryWriter(new FileStream(Rendered, FileMode.CreateNew));
                    return;
                }
                if (requestedFrame < 0) return;
                var state = animator.GetCurrentAnimatorStateInfo(0);
                Require(hook.PositionCorrectionActive && hook.LastError == "" && view.targetTexture == target
                    && view.actualRenderingPath == RenderingPath.Forward && state.fullPathHash == observedState
                    && Mathf.Abs(state.normalizedTime - requestedSample / (float)UccRegisteredAnimatorSampler.Samples) < .00001f
                    && requestedFrame == Time.frameCount && hook.CompletedFrame == requestedFrame && hook.CompletedCamera == cameraId,
                    "Corrected native buffer or camera did not belong to the current requested draw");
                byte[] bytes = ReadDrawnBuffer();
                if (litProbe) {
                    Require(UccNativeMeshIdentity.Hash(bytes) == litPoseBufferSha256,
                        "Changing the light at the same pose changed the actual draw geometry");
                    Require(ChangedLighting(litReference, Raster()), "The lit corrected mesh did not respond to a different light at the same pose");
                    Require(ChangedMotion(litReference, motionReference), "Opposite corrected poses did not change the rendered image");
                    Publish();
                    Finish(0, null);
                    return;
                }
                long offset = output.BaseStream.Position;
                WriteDrawnVertices(bytes);
                rows.Add(new Row {
                    sample = requestedSample, engine_frame = requestedFrame, camera_id = cameraId,
                    completed_frame = hook.CompletedFrame, completed_camera = hook.CompletedCamera, offset = offset,
                });
                if (requestedSample == LightProbeSample) {
                    litReference = Raster();
                    litPoseBufferSha256 = UccNativeMeshIdentity.Hash(bytes);
                }
                if (requestedSample == OppositeSample) motionReference = Raster();
                requestedFrame = -1;
            } catch (Exception error) { Finish(2, error); }
        }

        static Vector3 ReadVector(byte[] bytes, int start) {
            return new Vector3(BitConverter.ToSingle(bytes, start), BitConverter.ToSingle(bytes, start+4),
                BitConverter.ToSingle(bytes, start+8));
        }

        static bool Finite(Vector3 value) => UccRegisteredAnimatorSampler.Finite(value.x)
            && UccRegisteredAnimatorSampler.Finite(value.y) && UccRegisteredAnimatorSampler.Finite(value.z);

        byte[] ReadDrawnBuffer() {
            GraphicsBuffer drawn = hook.DrawVertexBuffer;
            int count = skin.sharedMesh.vertexCount;
            Require(drawn != null && drawn.count == count && drawn.stride == NativeStride && BitConverter.IsLittleEndian,
                "Actual corrected draw buffer layout changed");
            var read = AsyncGPUReadback.Request(drawn);
            read.WaitForCompletion();
            Require(!read.hasError, "Actual corrected draw buffer could not be read");
            byte[] bytes = read.GetData<byte>().ToArray();
            Require(bytes.Length == count * NativeStride, "Corrected native GPU readback lost vertex rows");
            return bytes;
        }

        void WriteDrawnVertices(byte[] bytes) {
            int count = skin.sharedMesh.vertexCount;
            var world = skin.rootBone.localToWorldMatrix;
            for (int index = 0; index < count; index++) {
                int start = index * NativeStride;
                var position = world.MultiplyPoint3x4(ReadVector(bytes, start));
                var normal = world.MultiplyVector(ReadVector(bytes, start+12));
                Require(Finite(position) && Finite(normal) && Mathf.Abs(normal.sqrMagnitude - 1f) < .002f,
                    "Corrected native draw contains a nonfinite position or nonunit normal");
                output.Write(position.x); output.Write(position.y); output.Write(position.z);
                output.Write(normal.x); output.Write(normal.y); output.Write(normal.z);
            }
        }

        Color32[] Raster() {
            var previous = RenderTexture.active;
            try {
                RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, Size, Size), 0, 0, false);
                return pixels.GetPixels32();
            } finally { RenderTexture.active = previous; }
        }

        static bool ChangedLighting(Color32[] before, Color32[] after) {
            if (before == null || after == null || before.Length != Size*Size || after.Length != before.Length) return false;
            int visible = 0, changed = 0;
            for (int index = 0; index < before.Length; index++) {
                var a = before[index]; var b = after[index];
                if (a.a != b.a) return false;
                if (a.a < 240) continue;
                visible++;
                if (a.r != b.r || a.g != b.g || a.b != b.b) changed++;
            }
            return visible > 0 && visible < before.Length && changed > 0;
        }

        static bool ChangedMotion(Color32[] before, Color32[] after) {
            if (before == null || after == null || before.Length != Size*Size || after.Length != before.Length) return false;
            bool visible = false, changed = false;
            for (int index = 0; index < after.Length; index++) {
                visible |= after[index].a >= 240;
                changed |= before[index].a != after[index].a;
            }
            return visible && changed;
        }

        void Publish() {
            output.Dispose();
            output = null;
            int count = skin.sharedMesh.vertexCount;
            Require(rows.Count == UccRegisteredAnimatorSampler.Samples
                && new FileInfo(Rendered).Length == (long)rows.Count * count * RecordStride,
                "Incomplete corrected native render stream");
            string digest;
            using (var stream = File.OpenRead(Rendered))
                using (var hash = SHA256.Create())
                    digest = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            var report = new Evidence {
                binding_sha256 = pins[0], native_mesh_sha256 = pins[1], topology_sha256 = pins[2], scene_sha256 = pins[3],
                unity = Application.unityVersion, graphics = SystemInfo.graphicsDeviceType.ToString(),
                native_vertices = count, corrected_sha256 = digest, rows = rows.ToArray(),
            };
            using (var writer = new StreamWriter(new FileStream(Result, FileMode.CreateNew))) writer.Write(JsonUtility.ToJson(report));
        }

        void Finish(int code, Exception error) {
            complete = true;
            if (error != null) Debug.LogException(error);
            terminalCode = code;
        }

        void FinishAfterRender() {
            int code = terminalCode.Value;
            terminalCode = null;
            Cleanup();
            string pending = Terminal + ".pending";
            using (var writer = new StreamWriter(new FileStream(pending, FileMode.CreateNew))) writer.Write(code);
            File.Move(pending, Terminal);
        }

        void Cleanup() {
            Camera.onPostRender -= Capture;
            output?.Dispose();
            output = null;
            if (changedCaptureRate) Time.captureFramerate = savedCaptureRate;
            changedCaptureRate = false;
            if (keyLight != null) keyLight.transform.rotation = lightOrientation;
            if (view != null && view.targetTexture == target) view.targetTexture = previousTarget;
            if (target != null) { target.Release(); Destroy(target); target = null; }
            if (pixels != null) { Destroy(pixels); pixels = null; }
        }

        void OnDestroy() { Cleanup(); }
    }
}
#endif

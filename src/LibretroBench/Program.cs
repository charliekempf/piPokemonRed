using System.Diagnostics;
using System.Runtime.InteropServices;

var root = FindRepoRoot();
var corePath = Path.GetFullPath(args.ElementAtOrDefault(0) ?? Path.Combine(root, "tools", "libretro", "gambatte_libretro.dll"));
var romPath = Path.GetFullPath(args.ElementAtOrDefault(1) ?? Path.Combine(root, "roms", "Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb"));
var piPath = Path.GetFullPath(args.ElementAtOrDefault(2) ?? Path.Combine(root, "data", "pi_1m_digits.txt"));
var loops = int.Parse(args.ElementAtOrDefault(3) ?? "5");

var piDigits = File.ReadAllText(piPath).Trim();
var inputFrames = BuildInputFrames(piDigits);
Console.WriteLine($"core: {corePath}");
Console.WriteLine($"rom: {romPath}");
Console.WriteLine($"pi digits: {piDigits.Length:N0}");
Console.WriteLine($"input frames per pass: {inputFrames.Length:N0}");

using var core = new LibretroCore(corePath, romPath, inputFrames);
core.RunFrames(600);

var stopwatch = Stopwatch.StartNew();
var totalFrames = 0L;
for (var loop = 0; loop < loops; loop++)
{
    totalFrames += core.RunFrames(inputFrames.Length);
}
stopwatch.Stop();

var fps = totalFrames / stopwatch.Elapsed.TotalSeconds;
var gameBoyFps = 4194304.0 / 70224.0;
Console.WriteLine($"bench frames: {totalFrames:N0}");
Console.WriteLine($"wall time: {stopwatch.Elapsed.TotalSeconds:F3}s");
Console.WriteLine($"fps: {fps:N0}");
Console.WriteLine($"real-time multiple: {fps / gameBoyFps:N0}x");

static string FindRepoRoot()
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir is not null)
    {
        if (Directory.Exists(Path.Combine(dir.FullName, ".git")))
        {
            return dir.FullName;
        }
        dir = dir.Parent;
    }

    return Directory.GetCurrentDirectory();
}

static uint[] BuildInputFrames(string digits)
{
    var frames = new uint[(digits.Length / 2) * 2];
    var output = 0;
    for (var index = 0; index + 1 < digits.Length; index += 2)
    {
        var value = (digits[index] - '0') * 10 + (digits[index + 1] - '0');
        frames[output++] = value switch
        {
            <= 53 => 1u << (int)RetroConstants.JoypadA,
            <= 63 => 1u << (int)RetroConstants.JoypadUp,
            <= 73 => 1u << (int)RetroConstants.JoypadDown,
            <= 83 => 1u << (int)RetroConstants.JoypadLeft,
            <= 93 => 1u << (int)RetroConstants.JoypadRight,
            <= 98 => 1u << (int)RetroConstants.JoypadB,
            _ => 1u << (int)RetroConstants.JoypadStart,
        };
        frames[output++] = 0;
    }

    return frames;
}

sealed unsafe class LibretroCore : IDisposable
{
    private readonly nint library;
    private readonly uint[] inputFrames;
    private int currentFrame;

    private readonly RetroEnvironment environment;
    private readonly RetroVideoRefresh videoRefresh;
    private readonly RetroAudioSample audioSample;
    private readonly RetroAudioSampleBatch audioSampleBatch;
    private readonly RetroInputPoll inputPoll;
    private readonly RetroInputState inputState;
    private readonly nint saveDirectoryPointer;

    private readonly RetroDeinit retroDeinit;
    private readonly RetroUnloadGame retroUnloadGame;
    private readonly RetroRun retroRun;

    public LibretroCore(string corePath, string romPath, uint[] inputFrames)
    {
        this.inputFrames = inputFrames;
        library = NativeLibrary.Load(corePath);

        environment = EnvironmentCallback;
        videoRefresh = static (_, _, _, _) => { };
        audioSample = static (_, _) => { };
        audioSampleBatch = static (_, _) => 0;
        inputPoll = static () => { };
        inputState = InputStateCallback;
        saveDirectoryPointer = Marshal.StringToHGlobalAnsi(Path.GetFullPath("saves"));

        Export<RetroSetEnvironment>("retro_set_environment")(environment);
        Export<RetroSetVideoRefresh>("retro_set_video_refresh")(videoRefresh);
        Export<RetroSetAudioSample>("retro_set_audio_sample")(audioSample);
        Export<RetroSetAudioSampleBatch>("retro_set_audio_sample_batch")(audioSampleBatch);
        Export<RetroSetInputPoll>("retro_set_input_poll")(inputPoll);
        Export<RetroSetInputState>("retro_set_input_state")(inputState);

        Export<RetroInit>("retro_init")();
        Export<RetroSetControllerPortDevice>("retro_set_controller_port_device")(0, RetroConstants.RetroDeviceJoypad);

        retroDeinit = Export<RetroDeinit>("retro_deinit");
        retroUnloadGame = Export<RetroUnloadGame>("retro_unload_game");
        retroRun = Export<RetroRun>("retro_run");

        var systemInfo = new RetroSystemInfo();
        Export<RetroGetSystemInfo>("retro_get_system_info")(ref systemInfo);
        var needsFullPath = systemInfo.need_fullpath;
        Console.WriteLine(
            $"core info: {Marshal.PtrToStringAnsi(systemInfo.library_name)} " +
            $"{Marshal.PtrToStringAnsi(systemInfo.library_version)}, " +
            $"extensions={Marshal.PtrToStringAnsi(systemInfo.valid_extensions)}, " +
            $"need_fullpath={needsFullPath}");

        var romBytes = needsFullPath ? [] : File.ReadAllBytes(romPath);
        fixed (byte* romPointer = romBytes)
        {
            var gameInfo = new RetroGameInfo
            {
                path = Marshal.StringToHGlobalAnsi(romPath),
                data = needsFullPath ? nint.Zero : (nint)romPointer,
                size = needsFullPath ? 0 : (nuint)romBytes.Length,
                meta = nint.Zero,
            };

            try
            {
                if (!Export<RetroLoadGame>("retro_load_game")(ref gameInfo))
                {
                    throw new InvalidOperationException("retro_load_game failed");
                }
            }
            finally
            {
                Marshal.FreeHGlobal(gameInfo.path);
            }
        }
    }

    public long RunFrames(int frameCount)
    {
        for (var index = 0; index < frameCount; index++)
        {
            retroRun();
            currentFrame++;
            if (currentFrame >= inputFrames.Length)
            {
                currentFrame = 0;
            }
        }

        return frameCount;
    }

    public void Dispose()
    {
        retroUnloadGame();
        retroDeinit();
        Marshal.FreeHGlobal(saveDirectoryPointer);
        NativeLibrary.Free(library);
    }

    private T Export<T>(string name)
        where T : Delegate
    {
        return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(library, name));
    }

    private bool EnvironmentCallback(uint command, nint data)
    {
        var baseCommand = command & 0xFFFF;
        switch (baseCommand)
        {
            case RetroConstants.RetroEnvironmentSetPixelFormat:
                return true;
            case RetroConstants.RetroEnvironmentGetSystemDirectory:
            case RetroConstants.RetroEnvironmentGetSaveDirectory:
                Marshal.WriteIntPtr(data, saveDirectoryPointer);
                return true;
            case RetroConstants.RetroEnvironmentGetCanDupe:
                Marshal.WriteByte(data, 1);
                return true;
            case RetroConstants.RetroEnvironmentSetSupportNoGame:
            case RetroConstants.RetroEnvironmentSetControllerInfo:
                return true;
            case RetroConstants.RetroEnvironmentSetCoreOptions:
            case RetroConstants.RetroEnvironmentGetVariable:
                return false;
            default:
                return false;
        }
    }

    private short InputStateCallback(uint port, uint device, uint index, uint id)
    {
        if (port != 0 || device != RetroConstants.RetroDeviceJoypad)
        {
            return 0;
        }

        return (inputFrames[currentFrame] & (1u << (int)id)) != 0 ? (short)1 : (short)0;
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate bool RetroEnvironment(uint command, nint data);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroVideoRefresh(nint data, uint width, uint height, nuint pitch);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroAudioSample(short left, short right);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate nuint RetroAudioSampleBatch(nint data, nuint frames);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroInputPoll();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate short RetroInputState(uint port, uint device, uint index, uint id);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetEnvironment(RetroEnvironment callback);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetVideoRefresh(RetroVideoRefresh callback);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetAudioSample(RetroAudioSample callback);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetAudioSampleBatch(RetroAudioSampleBatch callback);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetInputPoll(RetroInputPoll callback);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetInputState(RetroInputState callback);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroInit();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroDeinit();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroGetSystemInfo(ref RetroSystemInfo systemInfo);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate bool RetroLoadGame(ref RetroGameInfo gameInfo);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroUnloadGame();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroRun();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void RetroSetControllerPortDevice(uint port, uint device);

    [StructLayout(LayoutKind.Sequential)]
    private struct RetroGameInfo
    {
        public nint path;
        public nint data;
        public nuint size;
        public nint meta;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RetroSystemInfo
    {
        public nint library_name;
        public nint library_version;
        public nint valid_extensions;
        [MarshalAs(UnmanagedType.I1)]
        public bool need_fullpath;
        [MarshalAs(UnmanagedType.I1)]
        public bool block_extract;
    }
}

static class RetroConstants
{
    public const uint RetroEnvironmentSetPixelFormat = 10;
    public const uint RetroEnvironmentGetSystemDirectory = 9;
    public const uint RetroEnvironmentGetSaveDirectory = 31;
    public const uint RetroEnvironmentSetSupportNoGame = 18;
    public const uint RetroEnvironmentSetControllerInfo = 35;
    public const uint RetroEnvironmentSetCoreOptions = 52;
    public const uint RetroEnvironmentGetVariable = 15;
    public const uint RetroEnvironmentGetCanDupe = 3;

    public const uint RetroPixelFormatXrgb8888 = 1;
    public const uint RetroDeviceJoypad = 1;

    public const uint JoypadB = 0;
    public const uint JoypadStart = 3;
    public const uint JoypadUp = 4;
    public const uint JoypadDown = 5;
    public const uint JoypadLeft = 6;
    public const uint JoypadRight = 7;
    public const uint JoypadA = 8;
}

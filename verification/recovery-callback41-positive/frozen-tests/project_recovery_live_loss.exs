# Test-only native runner. Compiles the exact frozen artifact's module prefix,
# then executes its unchanged entry point while a private file-triggered observer
# can kill ONE actual project Store. It adds no product API or recovery behavior.
[artifact, payload] = System.argv()
bytes = File.read!(artifact)
[prefix, entry] = String.split(bytes, "\nunless Code.ensure_loaded?(ADHD.CLI) do", parts: 2)
Code.compile_string(prefix, artifact)
System.argv([payload])

defmodule RecoveryLiveLoss do
  def watch(config) do
    arm = config <> ".kill-target"
    if File.exists?(arm) do
      %{"project_id" => id, "nonce" => nonce} = ADHD.JSON.decode!(File.read!(arm))
      pid = ADHD.Store.writer(ADHD.Config.root(), id)
      true = is_pid(pid)
      monitor = Process.monitor(pid)
      Process.exit(pid, :kill)
      receive do
        {:DOWN, ^monitor, :process, ^pid, :killed} -> :ok
      after
        5000 -> raise "Actual project Store did not terminate"
      end
      File.rm!(arm)
      File.write!(config <> ".target-down", JSON.encode!(%{
        "project_id" => id, "nonce" => nonce, "reason" => "killed",
        "store_pid" => inspect(pid), "vm_pid" => System.pid()
      }))
    end
    Process.sleep(20)
    watch(config)
  end
end

["serve", config] = ADHD.JSON.decode!(payload)
spawn(fn -> RecoveryLiveLoss.watch(config) end)
Code.eval_string("unless Code.ensure_loaded?(ADHD.CLI) do" <> entry, [], file: artifact)

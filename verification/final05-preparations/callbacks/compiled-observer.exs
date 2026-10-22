# Test-only compiled boot; unchanged actual Store-loss watcher.
[artifact, payload] = System.argv()
["serve", config] = JSON.decode!(payload)
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

spawn(fn -> RecoveryLiveLoss.watch(config) end)
System.argv([artifact, payload])
Code.eval_file("/runtime/adhd/boot.exs")

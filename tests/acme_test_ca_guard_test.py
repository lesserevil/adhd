"""Pure fork-guard checks: never call real prctl, fork, signal or exit."""
import signal
import unittest
from unittest.mock import Mock,patch
import acme_test_ca as fixture
class Guard(unittest.TestCase):
 def test_live_expected_parent_sets_kill_then_checks_parent(self):
  calls=[];prctl=lambda *args:calls.append(args) or 0
  with patch.object(fixture.os,'getppid',return_value=111),patch.object(fixture.os,'_exit',side_effect=AssertionError('No exit')):
   fixture.parent_death_guard(111,prctl)()
  self.assertEqual(calls,[(1,signal.SIGKILL,0,0,0)])
 def test_dead_replaced_parent_exits_before_exec(self):
  prctl=Mock(return_value=0)
  with patch.object(fixture.os,'getppid',return_value=1),patch.object(fixture.os,'_exit',side_effect=SystemExit) as exit:
   with self.assertRaises(SystemExit):fixture.parent_death_guard(111,prctl)()
  exit.assert_called_once_with(127);prctl.assert_called_once_with(1,signal.SIGKILL,0,0,0)
 def test_prctl_failure_never_executes_child(self):
  with patch.object(fixture.os,'getppid') as parent,patch.object(fixture.os,'_exit',side_effect=SystemExit) as exit:
   with self.assertRaises(SystemExit):fixture.parent_death_guard(111,Mock(return_value=-1))()
  exit.assert_called_once_with(126);parent.assert_not_called()
if __name__=='__main__':unittest.main()

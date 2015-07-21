
# LLDB UI state in the Vim user interface.
#
# FIXME: implement WatchlistPane to displayed watched expressions
# FIXME: define interface for interactive panes, like catching enter
#        presses to change selected frame/thread...
#

import os, re
from vim_signs import *
from ui_helper import *

def is_same_file(a, b):
  """ returns true if paths a and b are the same file """
  a = os.path.realpath(a)
  b = os.path.realpath(b)
  return a in b or b in a

class UI:
  _content_map = {
      "backtrace": ( "command", ["bt", ""] ),
      "breakpoints": ( "command", ["breakpoint", "list"] ),
      "disassembly": ( "command", ["disassemble", "-c 20 -p"] ),
      "threads": ( "command", ["thread", "list"] ),
      "locals": ( "cb_on_target", get_locals_content ),
      "registers": ( "cb_on_target", get_registers_content ),
  }

  def __init__(self, vifx):
    """ Declare UI state variables """
    self.vifx = vifx

    self.buf_map = {}

    # Currently shown signs
    self.bp_signs = {} # maps (bufnr, line) -> <BreakpointSign object>
    self.bp_list = {} # maps (bufnr, line) -> [<SBBreakpoint object>, ...]
    self.pc_signs = {}

  def buf_map_check(self):
    if not self.buf_map:
      self.buf_map = self.vifx.buf_init()

  def update_pc(self, target, jump2pc):
    """ Place the PC sign on the PC location of each thread's selected frame.
        If jump2pc is True, the cursor should (FIXME) move to the PC location
        in the selected frame of the selected thread.
    """

    # Clear all existing PC signs
    for sign in self.pc_signs.values():
      sign.hide()
    self.pc_signs = {}

    if target is None or not target.IsValid():
      return
    process = target.GetProcess()
    if process is None or not process.IsValid() or not process.is_alive:
      return

    # Show a PC marker for each thread
    for thread in process:
      loc = get_pc_source_loc(thread)
      if not loc:
        # no valid source locations for PCs. hide all existing PC markers
        continue

      (tid, fname, line, col) = loc
      self.vifx.logger.info("Got pc loc: %s" % repr(loc))
      is_selected = thread.GetIndexID() == process.GetSelectedThread().GetIndexID()
      if os.path.exists(fname):
        bufnr = self.vifx.buffer_add(fname)
      else:
        continue

      sign = PCSign(self.vifx, bufnr, line, is_selected)
      self.pc_signs[(bufnr, line)] = sign

      if is_selected and jump2pc:
        self.vifx.sign_jump(bufnr, sign.id)

  def update_breakpoints(self, target, hard_update=False):
    """ Decorates buffer with signs corresponding to breakpoints in target. """

    self.bp_list = {}
    if target is None or not target.IsValid():
      for (key, sign) in self.bp_signs.items():
        if not sign.hidden:
          sign.hide()
      return

    needed_bps = {}
    for bp_index in range(target.GetNumBreakpoints()):
      bp = target.GetBreakpointAtIndex(bp_index)
      bplocs = get_bploc_tuples(bp, self.vifx.log)
      for (is_resolved, filepath, line) in bplocs:
        if filepath and os.path.exists(filepath):
          bufnr = self.vifx.buffer_add(filepath)
          key = (bufnr, line)
          needed_bps[key] = is_resolved
          if self.bp_list.has_key(key):
            self.bp_list[key].append(bp)
          else:
            self.bp_list[key] = [ bp ]

    # Hide all (outdated) breakpoint signs
    new_bps = needed_bps
    bp_signs = self.bp_signs.copy()
    for (key, sign) in bp_signs.items():
      if hard_update or not new_bps.has_key(key) or sign.resolved != new_bps[key]:
        sign.hide()
        del self.bp_signs[key]
      else:
        if bp_signs[key].hidden:
          bp_signs[key].show()
        del new_bps[key]

    # Show all (new) breakpoint signs
    for ((bufnr, line), resolved) in new_bps.items():
      self.bp_signs[(bufnr, line)] = BreakpointSign(self.vifx, bufnr, line, resolved,
                                                    self.pc_signs.has_key((bufnr, line)))

  def update_buffer(self, buf, target, commander):
    self.buf_map_check()

    content = UI._content_map[buf]
    if content[0] == 'command':
      results = get_command_content(content[1], target, commander)
      if buf == 'breakpoints':
        self.update_breakpoints(target)
    elif content[0] == 'cb_on_target':
      results = content[1](target)
    bufnr = self.buf_map[buf]

    def update_mapper(b):
      if b.number == bufnr:
        b.options['ma'] = True
        b[:] = results
        b.options['ma'] = False
        raise StopIteration

    self.vifx.map_buffers(update_mapper)

  def update(self, target, commander, status='', jump2pc=False, exclude_buf=[]):
    """ Updates signs, buffers, and prints status to the vim status line. """
    self.update_pc(target, jump2pc)

    for buf in UI._content_map.keys():
      if buf not in exclude_buf:
        self.update_buffer(buf, target, commander)

    if len(status) > 0:
      self.vifx.log(status, 0)

# vim:et:ts=2:sw=2

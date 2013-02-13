#!/usr/bin/env python
# This software is hereby released into the public domain. No warranties apply.

import pyudev
import os
import Queue
import threading
import time

class UDEVMonitor(object):
  """
  A UDEVMonitor can be used to listen to USB connect / disconnect events
  and assign them callbacks or operating system commands.
  """

  def __init__(self, cmd_connect, cmd_disconnect, log_function=None):
    """
    cmd_connect and cmd_disconnect map USB ID strings in hexadecimal
    format (<vendor id>:<product id>, e.g. 045e:078c) to either
    strings that will be executed directly with system.os() or to
    callback functions on connect / disconnect of the given device.
    
    log must be a function of the type f(str); it will be called with loggable
    information.
    
    Warning: the callback functions will be called from an internal
    thread!
    """
    self.cmd_connect = cmd_connect
    self.cmd_disconnect = cmd_disconnect
    self.log_function = log_function
    self.queue = Queue.Queue() # event queue
    self.connected = set() # set of connected devices

  def _log(self, msg):
    if self.log_function is not None:
      self.log_function(msg)

  def _enqueue_event(self, action, device):
    self.queue.put((action, device))
    
  def _handle_event(self, action, device):
    if "PRODUCT" not in device:
      return # unknown usb device?
    
    # transform <id>/<id> to 4-digit:4-digit usbid so we can match it
    usbid = ":".join("%04x" % int(i,16) for i in device["PRODUCT"].split("/")[0:2])

    if action == "add" and usbid in self.cmd_connect and usbid not in self.connected:
      self._log("Device %s connected" % usbid)
      self.connected.add(usbid)
      action = self.cmd_connect[usbid]
      if isinstance(action, str):
        os.system(action)
      else:
        action()
        
    elif action == "remove" and usbid in self.cmd_disconnect and usbid in self.connected:
      self._log("Device %s disconnected" % usbid)
      self.connected.remove(usbid)
      action = self.cmd_disconnect[usbid]
      if isinstance(action, str):
        os.system(action)
      else:
        action()

  def start(self):
    """
    Start the observer and queue processing threads.
    
    TODO: We could check the current state of all devices and run their connect/disconnect
    commands accordingly. This should ideally be configurable using flags
    (run_connect/run_disconnect) or using some other initial_connect dict.
    
    TODO: At the moment, this method blocks forever, KeyboardInterrupt does not work
    and you can only stop it by performing a kill (haven't tried calling stop).
    """
    
    class QueueProcessor(threading.Thread):
      def run(processor_self, *args):
        while True:
          params = self.queue.get()
          
          if params is None:
            break
            
          self._handle_event(*params)
          self.queue.task_done()      


    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="usb")

    self.queue_processor = QueueProcessor()
    self.queue_processor.start()
        
    try:
      while True:
        self.observer = pyudev.MonitorObserver(monitor, self._enqueue_event)
        try:
          self.observer.start() # this will start a new thread
          self.observer.join() # only join observer thread, queue processor will be killed
        except KeyboardInterrupt:
          self.stop()
          break
        except:
          pass
        time.sleep(1) # sleep in case the thread was killed (e.g. by suspend)
    except KeyboardInterrupt:
      self.stop()

  def stop(self):
    self._log("Exiting...")
    self.queue.put(None)
    self.queue_processor.join()
    self._log("Shut down queue")
    self.observer.send_stop()
    self.observer.join()
    self._log("Shut down udev observer")


if __name__ == "__main__":
  # demo and my custom setup

  cmd_connect = {}
  cmd_disconnect = {}

  # lenovo kb (home)
  cmd_connect["04b3:301b"] = """
          xrandr --output LVDS1 --off
          xrandr --output VGA1 --auto
          setxkbmap -model thinkpad -layout "us,at" -option "grp:switch"
  """
  cmd_disconnect["04b3:301b"] = """
          xrandr --output LVDS1 --auto
          xrandr --output VGA1 --off
          setxkbmap -model pc105 -layout "at,ro" -option
  """

  # microsoft kb (office)
  cmd_connect["045e:078c"] = """
          xrandr --output LVDS1 --off
          xrandr --output VGA1 --auto
  """
  cmd_disconnect["045e:078c"] = """
          xrandr --output LVDS1 --auto
          xrandr --output VGA1 --off
  """
  
  def log(msg):
    print msg
  
  UDEVMonitor(cmd_connect, cmd_disconnect, log).start()

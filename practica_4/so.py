#!/usr/bin/env python

from hardware import *
import log




## emulates a compiled program
class Program():

    def __init__(self, name, instructions):
        self._name = name
        self._instructions = self.expand(instructions)

    @property
    def name(self):
        return self._name

    @property
    def instructions(self):
        return self._instructions

    def addInstr(self, instruction):
        self._instructions.append(instruction)

    def expand(self, instructions):
        expanded = []
        for i in instructions:
            if isinstance(i, list):
                ## is a list of instructions
                expanded.extend(i)
            else:
                ## a single instr (a String)
                expanded.append(i)

        ## now test if last instruction is EXIT
        ## if not... add an EXIT as final instruction
        last = expanded[-1]
        if not ASM.isEXIT(last):
            expanded.append(INSTRUCTION_EXIT)

        return expanded

    def __repr__(self):
        return "Program({name}, {instructions})".format(name=self._name, instructions=self._instructions)


## emulates an Input/Output device controller (driver)
class IoDeviceController():

    def __init__(self, device):
        self._device = device
        self._waiting_queue = []
        self._currentPCB = None

    def runOperation(self, pcb, instruction):
        pair = {'pcb': pcb, 'instruction': instruction}
        # append: adds the element at the end of the queue
        self._waiting_queue.append(pair)
        # try to send the instruction to hardware's device (if is idle)
        self.__load_from_waiting_queue_if_apply()

    def getFinishedPCB(self):
        finishedPCB = self._currentPCB
        self._currentPCB = None
        self.__load_from_waiting_queue_if_apply()
        return finishedPCB

    def __load_from_waiting_queue_if_apply(self):
        if (len(self._waiting_queue) > 0) and self._device.is_idle:
            ## pop(): extracts (deletes and return) the first element in queue
            pair = self._waiting_queue.pop(0)
            #print(pair)
            pcb = pair['pcb']
            instruction = pair['instruction']
            self._currentPCB = pcb
            self._device.execute(instruction)


    def __repr__(self):
        return "IoDeviceController for {deviceID} running: {currentPCB} waiting: {waiting_queue}".format(deviceID=self._device.deviceId, currentPCB=self._currentPCB, waiting_queue=self._waiting_queue)

## emulates the  Interruptions Handlers
class AbstractInterruptionHandler():
    def __init__(self, kernel):
        self._kernel = kernel

    @property
    def kernel(self):
        return self._kernel

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))


class KillInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):

        log.logger.info(" Program Finished ")
        killedPCB = self.kernel.pcbTable.runningPCB
        self.kernel.dispatcher.save(killedPCB)
        killedPCB.state = "terminated"
        self.kernel.pcbTable.runningPCB = None
        if(not self.kernel.scheduler.isEmpty()):
            nextPCB = self.kernel.scheduler.getNext()
            nextPCB.state = "running"
            self.kernel.pcbTable.runningPCB = nextPCB
            self.kernel.dispatcher.load(nextPCB)


class IoInInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):

        program = irq.parameters
        pcb = self.kernel.pcbTable.runningPCB
        pcb.state = "waiting"
        self.kernel.dispatcher.save(pcb)
        self.kernel.pcbTable.runningPCB = None
        self.kernel.ioDeviceController.runOperation(pcb, program)
        if(not self.kernel.scheduler.isEmpty()):
         nextPCB = self.kernel.scheduler.getNext()
         nextPCB.state = "running"
         self.kernel.pcbTable.runningPCB = nextPCB
         self.kernel.dispatcher.load(nextPCB)
        log.logger.info(self.kernel.ioDeviceController)


class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):

       pcb = self.kernel.ioDeviceController.getFinishedPCB()
       if(self.kernel.pcbTable.runningPCB == None):
           pcb.state = "running"
           self.kernel.pcbTable.runningPCB = pcb
           self.kernel.dispatcher.load(pcb)
       else:
           if(not self.kernel.scheduler.mustExpropiated(self.kernel.pcbTable.runningPCB,pcb)):
            pcb.state = "ready"
            self.kernel.scheduler.add(pcb)
           else:
               expropiatedPCB = self.kernel.pcbTable.runningPCB
               expropiatedPCB.state = "ready"
               self.kernel.dispatcher.save(expropiatedPCB)
               self.kernel.scheduler.add(expropiatedPCB)
               pcb.state = "running"
               self.kernel.pcbTable.runningPCB = pcb
               self.kernel.dispatcher.load(pcb)

class NewInterruptHandler(AbstractInterruptionHandler):

    def execute(self,irq):

        programParam = irq.parameters
        program = programParam['program']
        priority = programParam['priority']
        pcb = Pcb(self.kernel.pcbTable.getNewPID(),priority)
        runningPCB = self.kernel.pcbTable.runningPCB
        pcb.path = program.name
        pcb.baseDir = self.kernel.loader.load(program)
        self.kernel.pcbTable.add(pcb)

        if(runningPCB == None):
           pcb.state = "running"
           self.kernel.pcbTable.runningPCB = pcb
           self.kernel.dispatcher.load(pcb)
        else:
           if(not self.kernel.scheduler.mustExpropiated(runningPCB,pcb)):
            pcb.state = "ready"
            self.kernel.scheduler.add(pcb)
           else:
            expropiatedPCB = runningPCB
            expropiatedPCB.state = "ready"
            self.kernel.dispatcher.save(expropiatedPCB)
            self.kernel.scheduler.add(expropiatedPCB)
            pcb.state = "running"
            self.kernel.pcbTable.runningPCB = pcb
            self.kernel.dispatcher.load(pcb)
        log.logger.info(self.kernel.pcbTable)

class TimeoutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):

        if self.kernel.scheduler.isEmpty():
            HARDWARE.timer.reset()
        else:
           outPCB = self.kernel.pcbTable.runningPCB
           self.kernel.dispatcher.save(outPCB)
           outPCB.state = "ready"
           self.kernel.scheduler.add(outPCB)
           nextPCB = self.kernel.scheduler.getNext()
           self.kernel.pcbTable.runningPCB = nextPCB
           nextPCB.state = "running"
           self.kernel.dispatcher.load(nextPCB)


class Dispatcher():


    def load(self,pcb):

        HARDWARE.timer.reset()
        HARDWARE.cpu.pc = pcb.pc
        HARDWARE.mmu.baseDir = pcb.baseDir


    def save(self,pcb):

        pcb.pc = HARDWARE.cpu.pc
        HARDWARE.cpu.pc = -1

class Node():

    def __init__(self,value):
        self._value = value
        self._next = None

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self,value):
        self._value = value

    @property
    def next(self):
        return self._next

    @next.setter
    def next(self,next):
        self._next = next

class Queue():

    def __init__(self):
        self._head = None
        self._tail = None
        self._size = 0

    def dequeue(self):
       temp = self._head.value
       if(self._size == 1):
           self._head = None
           self._tail = None
       else:
           self._head = self._head.next
       self._size-=1
       return temp

    def enqueue(self,item):
       temp = Node(item)
       if(self.isEmpty()):
         self._head = temp
         self._tail = temp
       else:
         self._tail.next = temp
         self._tail = temp
       self._size+=1

    def isEmpty(self):
        return self._size == 0

    def peek(self):
        return self._head.value

class Pcb():

    def __init__(self, pid, priority):
        self._pid = pid
        self._baseDir = 0
        self._pc = 0
        self._priority = priority
        self._state = "new"
        self._path = ""

    @property
    def pid(self):

        return self._pid

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        self._state = state

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self,path):
        self._path = path

    @property
    def baseDir(self):
        return self._baseDir

    @baseDir.setter
    def baseDir(self, baseDir):
        self._baseDir = baseDir

    @property
    def pc(self):
        return self._pc

    @pc.setter
    def pc(self,cp):
        self._pc = cp

    @property
    def priority(self):
       return self._priority

class PCBTable():

    def __init__(self):
        self._pcbTable = {}
        self._runningPCB = None
        self._pid = -1

    def getNewPID(self):
        self._pid  += 1
        return self._pid

    @property
    def runningPCB(self):
        return self._runningPCB

    @runningPCB.setter
    def runningPCB(self,pcb):
        self._runningPCB = pcb

    def getPid(self,pid):
        return self._pcbTable.get(pid)

    def add(self,pcb):
        self._pcbTable[pcb.pid] = pcb

    def remove(self,pid):
        self._pcbTable[pid]

    def __repr__(self):
        return tabulate(enumerate(self._pcbTable),"pcbTable for {pcbTable} running : {runningPCB}".format(pcbTable = self._pcbTable, runningPCB=self._runningPCB))
class Loader():
    def __init__(self):
        self._freeDir = 0

    def load(self, program):
        baseDir = self._freeDir
        instructions = program.instructions
        for inst in instructions:
          HARDWARE.memory.put(self.freeDir, inst)
          self._freeDir += 1
        log.logger.info(HARDWARE.memory)
        return baseDir

    @property
    def freeDir(self):
        return self._freeDir

class Scheduler():

    def __init__(self):
        self._readyQueue = Queue()

    def add(self,pcb):
        pass

    def mustExpropiated(self,runPCB,addPCB):
        pass

    def getNext(self):
        pass

    def isEmpty(self):
        pass

    @property
    def readyQueue(self):
        return self._readyQueue

class  FirstComeFirstServed(Scheduler):

      def add(self,pcb):
         self.readyQueue.enqueue(pcb)

      def mustExpropiated(self,runPCB,addPCB):
          return False

      def getNext(self):
          return self.readyQueue.dequeue()

      def isEmpty(self):
          return self.readyQueue.isEmpty()

class RoundRobin(Scheduler):

    def __init__(self, quantum):
        super().__init__()
        HARDWARE.timer.quantum = quantum

    def add(self, pcb):
        self.readyQueue.enqueue(pcb)

    def mustExpropiated(self, runPCB, addPCB):
        return False

    def getNext(self):
        return self.readyQueue.dequeue()

    def isEmpty(self):
        return self.readyQueue.isEmpty()

class PrioritySchedule(Scheduler):

    def __init__(self):
       super().__init__()

       self._priorit1 = Queue()
       self._priorit2 = Queue()
       self._priorit3 = Queue()
       self._priorit4 = Queue()
       self._priorit5 = Queue()
       self._queues = {1: self._priorit1, 2: self._priorit2,
                       3: self._priorit4, 4: self._priorit4,
                       5: self._priorit5}

    def add(self,pcb):
        ''' for i in range(1,6):
            if(pcb.priority == i):
                self._queues.get(i).enqueue(pcb)'''
        self._queues[pcb.priority].enqueue(pcb)

    def mustExpropiated(self,runPCB,addPCB):
        pass

    def getNext(self):
        if (not self._priorit1.isEmpty()):
            return self._priorit1.dequeue()
        elif(not self._priorit2.isEmpty()):
            return self._priorit2.dequeue()
        elif (not self._priorit3.isEmpty()):
            return self._priorit3.dequeue()
        elif (not self._priorit4.isEmpty()):
            return self._priorit4.dequeue()
        else:
            return self._priorit5.dequeue()

    def isEmpty(self):
        for i in range(1,6):
            if(not self._queues.get(i).isEmpty()):
                return False
        return True


    def aging(self):
      '''if(not self._priorit2.isEmpty()):
       temp2 = self._priorit2.dequeue()
       self._priorit1.enqueue(temp2)
      if (not self._priorit3.isEmpty()):
       temp3 = self._priorit3.dequeue()
       self._priorit2.enqueue(temp3)
      if (not self._priorit4.isEmpty()):
       temp4 = self._priorit4.dequeue()
       self._priorit3.enqueue(temp4)
      if (not self._priorit5.isEmpty()):
       temp5 = self._priorit5.dequeue()
       self._priorit4.enqueue(temp5)'''
      for i in range(2,6):
          if(not self._queues.get(i).isEmpty()):
             temp = self._queues.get(i).dequeue()
             self._queues.get(i-1).enqueue(temp)


'''class GanttDiagram():
   
   def __init__(self):
      self._table = {}
      HARDWARE.clock.addSubscriber(self)
      self._state = 0

   def add(self,pcb):
       self._table[self.kernel.pcbTable.getPid(pcb)] = pcb.state

   def tick(self,tickNmbr):

       for key in self._table:
           self._state
'''


      
   

class PreemptivePriority(PrioritySchedule):

    def add(self,pcb):
        super().add(pcb)

    def getNext(self):
        temp = super().getNext()
        super().aging()
        return temp

    def isEmpty(self):
        return super().isEmpty()

    def mustExpropiated(self,runPCB,addPCB):
        return addPCB.priority < runPCB.priority

class NoPreemptivePriority(PrioritySchedule):

    def add(self,pcb):
        super().add(pcb)

    def getNext(self):
        temp = super().getNext()
        super().aging()
        return temp

    def isEmpty(self):
        return super().isEmpty()

    def mustExpropiated(self,runPCB,addPCB):
        return False



# emulates the core of an Operative System
class Kernel():

    def __init__(self, scheduler):

        ## setup interruption handlers
        killHandler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, killHandler)

        ioInHandler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, ioInHandler)

        ioOutHandler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, ioOutHandler)

        newHandler = NewInterruptHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE, newHandler)

        timeOutHandler = TimeoutInterruptionHandler(self)
        HARDWARE.interruptVector.register(TIMEOUT_INTERRUPTION_TYPE,timeOutHandler)

        #create a PCBTable
        self._pcbTable = PCBTable()

        #create a Loader
        self._loader = Loader()

        #create a ReadyQueue
        ##self._readyQueue = ReadyQueue()

        self._scheduler = scheduler

        #create a Dispatcher
        self._dispatcher = Dispatcher()

        ## controls the Hardware's I/O Device
        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)

    @property
    def ioDeviceController(self):
        return self._ioDeviceController

    @property
    def pcbTable(self):
        return self._pcbTable

    @property
    def loader(self):
        return self._loader

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def dispatcher(self):
        return self._dispatcher

    ## emulates a "system call" for programs execution
    def run(self, program, priority):

        newProgram = {'program':program,'priority':priority}
        newIRQ = IRQ(NEW_INTERRUPTION_TYPE, newProgram)
        HARDWARE.interruptVector.handle(newIRQ)
        log.logger.info("\n Executing program: {name}".format(name=program.name))
        log.logger.info(HARDWARE)


    def __repr__(self):
        return "Kernel "

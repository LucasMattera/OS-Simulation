#!/usr/bin/env python

from hardware import *
import log
import math



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

        frameToFree = []
        log.logger.info(" Program Finished ")
        killedPCB = self.kernel.pcbTable.runningPCB
        self.kernel.dispatcher.save(killedPCB)
        for key, value in self.kernel.memoryManager.getPageTable(killedPCB.pid).pageTable.items():
            frameToFree.append(value)
        self.kernel.memoryManager.freeFrame(frameToFree)
        killedPCB.state = "terminated"
        self.kernel.pcbTable.runningPCB = None
        log.logger.error("freeFrameList :")
        log.logger.info(self.kernel.memoryManager)
        if(not self.kernel.scheduler.isEmpty()):
            nextPCB = self.kernel.scheduler.getNext()
            nextPCB.state = "running"
            self.kernel.pcbTable.runningPCB = nextPCB
            self.kernel.dispatcher.load(nextPCB,self.kernel.memoryManager.getPageTable(nextPCB.pid))


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
         self.kernel.dispatcher.load(nextPCB,self.kernel.memoryManager.getPageTable(nextPCB.pid))
        log.logger.info(self.kernel.ioDeviceController)


class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):

       pcb = self.kernel.ioDeviceController.getFinishedPCB()
       if(self.kernel.pcbTable.runningPCB == None):
           pcb.state = "running"
           self.kernel.pcbTable.runningPCB = pcb
           self.kernel.dispatcher.load(pcb,self.kernel.memoryManager.getPageTable(pcb.pid))
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
               self.kernel.dispatcher.load(pcb,self.kernel.memoryManager.getPageTable(pcb.pid))

class NewInterruptHandler(AbstractInterruptionHandler):

    def execute(self,irq):

        priority = irq.parameters.get('priority')
        pcb = Pcb(self.kernel.pcbTable.getNewPID(),priority)
        runningPCB = self.kernel.pcbTable.runningPCB
        pcb.path = irq.parameters.get('path')
        self.kernel.loader.load(pcb)
        self.kernel.pcbTable.add(pcb)
        if(runningPCB == None):
           pcb.state = "running"
           self.kernel.pcbTable.runningPCB = pcb
           self.kernel.dispatcher.load(pcb,self.kernel.memoryManager.getPageTable(pcb.pid))
           self.kernel.ganttDiagram.addToTable(pcb)
        else:
           if(not self.kernel.scheduler.mustExpropiated(runningPCB,pcb)):
            pcb.state = "ready"
            self.kernel.scheduler.add(pcb)
            self.kernel.ganttDiagram.addToTable(pcb)
           else:
            print(pcb.pid)
            expropiatedPCB = runningPCB
            expropiatedPCB.state = "ready"
            self.kernel.dispatcher.save(expropiatedPCB)
            self.kernel.scheduler.add(expropiatedPCB)
            pcb.state = "running"
            self.kernel.pcbTable.runningPCB = pcb
            self.kernel.dispatcher.load(pcb,self.kernel.memoryManager.getPageTable(pcb.pid))
            self.kernel.ganttDiagram.addToTable(pcb)

        log.logger.info(self.kernel.pcbTable)
        log.logger.info(self.kernel.memoryManager)

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
           self.kernel.dispatcher.load(nextPCB,self.kernel.memoryManager.getPageTable(nextPCB.pid))


class Dispatcher():

    def load(self,pcb,pageTableDelPCB):

        HARDWARE.mmu.resetTLB()
        for page in pageTableDelPCB.pageTable:
         HARDWARE.mmu.setPageFrame(page,pageTableDelPCB.pageTable[page])
        HARDWARE.timer.reset()
        HARDWARE.cpu.pc = pcb.pc

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

class FileSystem():

    def __init__(self):
        self._dirs = {}

    def write(self,path,program):
        self._dirs[path]=program

    def read(self,path):
        return self._dirs.get(path)

class Pcb():

    def __init__(self, pid, priority):
        self._pid = pid
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

    def allTerminated(self):
        estanTerminados = True
        for pid in self._pcbTable:
            estanTerminados = estanTerminados and self._pcbTable[pid].state == 'terminated'
        return estanTerminados
    def __repr__(self):
        return tabulate(enumerate(self._pcbTable),"pcbTable for {pcbTable} running : {runningPCB}".format(pcbTable = self._pcbTable, runningPCB=self._runningPCB))

class MemoryManager():

    def __init__(self,frameSize):
        self._freeFrameList = []
        self._usedFrames = []
        self._pageTable = {}
        self._frameSize = frameSize
        HARDWARE.mmu.frameSize = frameSize
        frameId = 0
        while frameId < HARDWARE.memory.memorySize()/frameSize:
            self._freeFrameList.append(frameId)
            frameId += 1

    def allocFrame(self,index):
        self._frameToUse = []
        for i in range(0,index):
            self._frameToUse.append(self._freeFrameList.pop())
        self._usedFrames.extend(self._frameToUse)
        return self._frameToUse

    def freeFrame(self,frames):
        for f in frames:
            self._usedFrames.remove(f)
        self._freeFrameList.extend(frames)

    def adequateFrames(self,index):
        return len(self._freeFrameList) >= index

    def putPageTable(self,pid,pageTable):
        self._pageTable[pid] = pageTable

    def getPageTable(self,pid):
        return self._pageTable[pid]

    @property
    def frameSize(self):
        return self._frameSize

    def __repr__(self):
        return tabulate(enumerate(self._freeFrameList),tablefmt='psql')

class Loader():

    def __init__(self,memoryManager,fileSystem):
        self._freeDir = 0
        self._fileSystem = fileSystem
        self._memoryManager = memoryManager

    def load(self, pcb):
        instructions = self._fileSystem.read(pcb.path).instructions
        lenInstructions = len(instructions)
        frameSize = self._memoryManager.frameSize
        progPages = math.ceil(lenInstructions / frameSize)

        if(self._memoryManager.adequateFrames(progPages)):
          pageID = 0
          frames = self._memoryManager.allocFrame(progPages)
          pageTable = PageTable()
          for frame in frames:
              pageTable.putPageTable(pageID,frame)
              pageID += 1
          self._memoryManager.putPageTable(pcb.pid,pageTable)

          numPage = 0
          for frame in frames:
            index = 0
            while index < 4:
             inst = instructions[numPage*frameSize + index]
             HARDWARE.memory.put(frame*frameSize+index, inst)
             index += 1
             if(lenInstructions <=((numPage*frameSize)+index)):
                 break
            numPage += 1
        log.logger.info(HARDWARE.memory)


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


class GanttDiagram():
   
   def __init__(self,pcbTable):
      self._table = {}
      self._pcbTable = pcbTable
      HARDWARE.clock.addSubscriber(self)
      
   
   @property
   def pcbTable(self):
      return self._pcbTable 
    
   @property
   def table(self):
      return self._table
   
   def addToTable(self, pcb):
      state = pcb.state
      if len(self._table) != 0:
         self.table[pcb.pid] = ['NotLoaded']
         for numberOfTicks in self._table[0]:
            self.table[pcb.pid].append('NotLoaded')

         self.table[pcb.pid].pop()
         self.table[pcb.pid].append(state)
      else:
         self.table[pcb.pid] = [state]

   def tick(self,tickNmbr):
        for key, value in self._table.items():
            state = self.pcbTable.getPid(key).state
            value.append(state)

        if self.pcbTable.allTerminated():
            log.logger.error('all terminated')
            HARDWARE.switchOff()
            log.logger.info(self)

   def __repr__(self):
        return tabulate(self._table, tablefmt='fancy_grid')

class PageTable():

    def __init__(self):
        self._pageTable = {}

    @property
    def pageTable(self):
        return self._pageTable

    def putPageTable(self,numPage,numFrame):
        self._pageTable[numPage]=numFrame

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

        #create a FileSystem
        self._fileSystem = FileSystem()

        #create Scheduler
        self._scheduler = scheduler

        #create a Dispatcher
        self._dispatcher = Dispatcher()

        ## controls the Hardware's I/O Device
        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)

        #create a MemoryManager
        self._memoryManager = MemoryManager(4)

        # create a Loader
        self._loader = Loader(self._memoryManager,self._fileSystem)

        # create gantt diagram
        self._ganttDiagram = GanttDiagram(self._pcbTable)

    @property
    def ioDeviceController(self):
        return self._ioDeviceController

    @property
    def memoryManager(self):
        return self._memoryManager

    @property
    def pcbTable(self):
        return self._pcbTable

    @property
    def fileSystem(self):
        return self._fileSystem

    @property
    def loader(self):
        return self._loader

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def dispatcher(self):
        return self._dispatcher

    @property
    def ganttDiagram(self):
        return self._ganttDiagram

    ## emulates a "system call" for programs execution
    def run(self, path, priority):

        newProgram = {'path':path,'priority':priority}
        newIRQ = IRQ(NEW_INTERRUPTION_TYPE, newProgram)
        HARDWARE.interruptVector.handle(newIRQ)
        log.logger.info("\n Executing program: {name}".format(name=path))
        log.logger.info(HARDWARE)


    def __repr__(self):
        return "Kernel "

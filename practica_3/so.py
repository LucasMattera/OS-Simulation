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
        self.kernel.pcbTable.remove(killedPCB.pid)
        self.kernel.pcbTable.runningPCB = None
        if(not self.kernel.readyQueue.isEmptyQ()):
            nextPCB = self.kernel.readyQueue.dequeue()
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


        print(pcb._pc)
        self.kernel.ioDeviceController.runOperation(pcb, program)


        print(pcb.pc)

        if(not self.kernel.readyQueue.isEmptyQ()):
         nextPCB = self.kernel.readyQueue.dequeue()
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
           pcb.state = "ready"
           self.kernel.readyQueue.enqueue(pcb)


class NewInterruptHandler(AbstractInterruptionHandler):

    def execute(self,irq):

        program = irq.parameters
        pcb = Pcb(self.kernel.pcbTable.getNewPID())
        pcb.path = program.name
        pcb.baseDir = self.kernel.loader.load(program)
        self.kernel.pcbTable.add(pcb)
        if(self.kernel.pcbTable.runningPCB == None):
           pcb.state = "running"
           self.kernel.pcbTable.runningPCB = pcb
           self.kernel.dispatcher.load(pcb)
        else:
           pcb.state = "ready"
           self.kernel.readyQueue.enqueue(pcb)

class Dispatcher():


    def load(self,pcb):

        HARDWARE.cpu.pc = pcb.pc
        HARDWARE.mmu.baseDir = pcb.baseDir


    def save(self,pcb):


        pcb.pc = HARDWARE.cpu.pc
        HARDWARE.cpu.pc = -1


class Pcb():

    def __init__(self, pid):
        self._pid = pid
        self._baseDir = 0
        self._pc = 0
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

class PCBTable():

    def __init__(self):
        self._pcbTable = []
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

    def getPid(self,pID):
        ## Refactoriar
        for pcb in self._pcbTable:
             if(pID == pcb.pid):
                 return pcb

    def add(self,pcb):
        self._pcbTable.append(pcb)

    def remove(self,pid):
        self._pcbTable.remove(self.getPid(pid))

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

class ReadyQueue():
    def __init__(self):
        self._readyQueue = []

    def enqueue(self, pcb):
        self._readyQueue.append(pcb)

    def dequeue(self):
        return self._readyQueue.pop(0)

    def isEmptyQ(self):
        return len(self._readyQueue) == 0

   ## def head(self):
       ## return self._readyQueue[0]

# emulates the core of an Operative System
class Kernel():

    def __init__(self):
        ## setup interruption handlers
        killHandler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, killHandler)

        ioInHandler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, ioInHandler)

        ioOutHandler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, ioOutHandler)

        newHandler = NewInterruptHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE, newHandler)

        #create a PCBTable
        self._pcbTable = PCBTable()

        #create a Loader
        self._loader = Loader()

        #create a ReadyQueue
        self._readyQueue = ReadyQueue()

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
    def readyQueue(self):
        return self._readyQueue

    @property
    def dispatcher(self):
        return self._dispatcher

    ## emulates a "system call" for programs execution
    def run(self, program):
        #self.load_program(program)


        newIRQ = IRQ(NEW_INTERRUPTION_TYPE, program)
        HARDWARE.interruptVector.handle(newIRQ)
        log.logger.info("\n Executing program: {name}".format(name=program.name))
        log.logger.info(HARDWARE)


    def __repr__(self):
        return "Kernel "

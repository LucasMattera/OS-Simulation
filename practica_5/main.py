from hardware import *
from so import *
import log


##
##  MAIN 
##
if __name__ == '__main__':
    log.setupLogger()
    log.logger.info('Starting emulator')

    ## setup our hardware and set memory size to 25 "cells"
    HARDWARE.setup(24)

    ## Switch on computer
    HARDWARE.switchOn()

    ## new create the Operative System Kernel
    # "booteamos" el sistema operativo
    kernel = Kernel(PreemptivePriority())
    ## no implemente El diagrama de gantt

    # Ahora vamos a intentar ejecutar 3 programas a la vez
    ##################
    prg1 = Program("prg1.exe", [ASM.CPU(3), ASM.IO(),ASM.CPU(1)])
    prg2 = Program("prg2.exe", [ASM.CPU(7)])
    prg3 = Program("prg3.exe", [ASM.CPU(4), ASM.IO(), ASM.CPU(1)])

    kernel.fileSystem.write("c:/prg1.exe", prg1)
    kernel.fileSystem.write("c:/prg2.exe", prg2)
    kernel.fileSystem.write("c:/prg3.exe", prg3)

    # execute all programs "concurrently"
    kernel.run("c:/prg1.exe",5)
    kernel.run("c:/prg2.exe",2)
    kernel.run("c:/prg3.exe",1)





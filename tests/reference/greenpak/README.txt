GreenHAL, an Amstrad CPC6128 HAL/PAL replacement on an SLG46826, by Bread80:
https://github.com/Bread80/GreenHAL (CERN-OHL-P v2, see LICENCE-GreenHAL.txt).
The .gp6 files are its Renesas Go Configure projects (TSSOP and STQFN), with
the 256-byte NVM image Go Configure made; GreenHALTests.txt is its test log,
identical to the log of the original Amstrad 40031 HAL.

tests/test_gpbits.py decodes the NVM images with cpldglue.gpbits' register
map and simulates them with its model, replaying the test log: every line
must match. That checks the matrix numbering, the LUT bit order, the DFF
settings, the multi-function cells' DFF mode and the pins against Go
Configure and the hardware.

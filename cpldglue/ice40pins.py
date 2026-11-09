"""iCE40 package pin tables.

Generated from KiCad's FPGA_Lattice symbol library (pin names and types) and
cross-checked against Project IceStorm's pinloc_db (icebox.py), which lists
the pins nextpnr can use as I/O: the two agree for every package here.
"""
# device -> {"io": [I/O pins], "names": {pin: name}, "types": {pin: KiCad pin type}}
ICE40_PINS = {
    "iCE40HX1K-TQ144": {
        "io": [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 31, 32, 33,
            34, 37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 50, 52, 56, 58, 60, 61, 62, 63, 64, 67,
            68, 70, 71, 73, 74, 75, 76, 78, 79, 80, 81, 87, 88, 90, 91, 93, 94, 95, 96, 97, 98, 99,
            101, 102, 104, 105, 106, 107, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122,
            128, 129, 134, 135, 136, 137, 138, 139, 141, 142, 143, 144],
        "names": {1: 'IOL_1A', 2: 'IOL_1B', 3: 'IOL_2A', 4: 'IOL_2B', 5: 'GND', 6: 'VCCIO_3', 7:
            'IOL_3A', 8: 'IOL_3B', 9: 'IOL_4A', 10: 'IOL_4B', 11: 'IOL_5A', 12: 'IOL_5B', 13:
            'GND', 14: 'GND', 15: 'NC', 16: 'NC', 17: 'NC', 18: 'NC', 19: 'IOL_6A', 20:
            'IOL_6B_GBIN7', 21: 'IOL_7A_GBIN6', 22: 'IOL_7B', 23: 'IOL_8A', 24: 'IOL_8B', 25:
            'IOL_9A', 26: 'IOL_9B', 27: 'VCC', 28: 'IOL_10A', 29: 'IOL_10B', 30: 'VCCIO_3', 31:
            'IOL_11A', 32: 'IOL_11B', 33: 'IOL_12A', 34: 'IOL_12B', 35: 'GNDPLL', 36: 'VCCPLL', 37:
            'IOB_24', 38: 'IOB_25', 39: 'IOB_26', 40: 'NC', 41: 'IOB_27', 42: 'IOB_28', 43:
            'IOB_29', 44: 'IOB_30', 45: 'IOB_31', 46: 'VCCIO_2', 47: 'IOB_32', 48: 'IOB_33', 49:
            'IOB_35_GBIN5', 50: 'IOB_36_GBIN4', 51: 'VCC', 52: 'IOB_34', 53: 'NC', 54: 'NC', 55:
            'NC', 56: 'IOB_37', 57: 'VCCIO_2', 58: 'IOB_38', 59: 'GND', 60: 'IOB_39', 61: 'IOB_40',
            62: 'IOB_41', 63: 'IOB_42_CBSEL0', 64: 'IOB_43_CBSEL1', 65: 'CDONE', 66: '~{CRESET_B}',
            67: 'IOB_44_SDO', 68: 'IOB_45_SDI', 69: 'GND', 70: 'IOB_46_SCK', 71: 'IOB_47_SS', 72:
            'VCC_SPI', 73: 'IOR_48', 74: 'IOR_49', 75: 'IOR_50', 76: 'IOR_51', 77: 'NC', 78:
            'IOR_52', 79: 'IOR_53', 80: 'IOR_54', 81: 'IOR_55', 82: 'NC', 83: 'NC', 84: 'NC', 85:
            'NC', 86: 'GND', 87: 'IOR_56', 88: 'IOR_57', 89: 'VCCIO_1', 90: 'IOR_58', 91: 'IOR_59',
            92: 'VCC', 93: 'IOR_60_GBIN3', 94: 'IOR_61_GBIN2', 95: 'IOR_62', 96: 'IOR_63', 97:
            'IOR_64', 98: 'IOR_65', 99: 'IOR_66', 100: 'VCCIO_1', 101: 'IOR_67', 102: 'IOR_68',
            103: 'GND', 104: 'IOR_69', 105: 'IOR_70', 106: 'IOR_71', 107: 'IOR_72', 108: 'VPP_2V5',
            109: 'VPP_FAST', 110: 'NC', 111: 'VCC', 112: 'IOT_73', 113: 'IOT_74', 114: 'IOT_75',
            115: 'IOT_76', 116: 'IOT_77', 117: 'IOT_78', 118: 'IOT_79', 119: 'IOT_80', 120:
            'IOT_81', 121: 'IOT_82', 122: 'IOT_83', 123: 'VCCIO_0', 124: 'NC', 125: 'NC', 126:
            'NC', 127: 'NC', 128: 'IOT_84_GBIN1', 129: 'IOT_85_GBIN0', 130: 'NC', 131: 'NC', 132:
            'GND', 133: 'VCCIO_0', 134: 'IOT_87', 135: 'IOT_88', 136: 'IOT_89', 137: 'IOT_90', 138:
            'IOT_91', 139: 'IOT_92', 140: 'GND', 141: 'IOT_93', 142: 'IOT_94', 143: 'IOT_95', 144:
            'IOT_96'},
        "types": {1: 'bidirectional', 2: 'bidirectional', 3: 'bidirectional', 4: 'bidirectional',
            5: 'power_in', 6: 'power_in', 7: 'bidirectional', 8: 'bidirectional', 9:
            'bidirectional', 10: 'bidirectional', 11: 'bidirectional', 12: 'bidirectional', 13:
            'passive', 14: 'passive', 15: 'no_connect', 16: 'no_connect', 17: 'no_connect', 18:
            'no_connect', 19: 'bidirectional', 20: 'bidirectional', 21: 'bidirectional', 22:
            'bidirectional', 23: 'bidirectional', 24: 'bidirectional', 25: 'bidirectional', 26:
            'bidirectional', 27: 'power_in', 28: 'bidirectional', 29: 'bidirectional', 30:
            'passive', 31: 'bidirectional', 32: 'bidirectional', 33: 'bidirectional', 34:
            'bidirectional', 35: 'power_in', 36: 'power_in', 37: 'bidirectional', 38:
            'bidirectional', 39: 'bidirectional', 40: 'no_connect', 41: 'bidirectional', 42:
            'bidirectional', 43: 'bidirectional', 44: 'bidirectional', 45: 'bidirectional', 46:
            'power_in', 47: 'bidirectional', 48: 'bidirectional', 49: 'bidirectional', 50:
            'bidirectional', 51: 'passive', 52: 'bidirectional', 53: 'no_connect', 54:
            'no_connect', 55: 'no_connect', 56: 'bidirectional', 57: 'passive', 58:
            'bidirectional', 59: 'passive', 60: 'bidirectional', 61: 'bidirectional', 62:
            'bidirectional', 63: 'bidirectional', 64: 'bidirectional', 65: 'open_collector', 66:
            'input', 67: 'bidirectional', 68: 'bidirectional', 69: 'passive', 70: 'bidirectional',
            71: 'bidirectional', 72: 'power_in', 73: 'bidirectional', 74: 'bidirectional', 75:
            'bidirectional', 76: 'bidirectional', 77: 'no_connect', 78: 'bidirectional', 79:
            'bidirectional', 80: 'bidirectional', 81: 'bidirectional', 82: 'no_connect', 83:
            'no_connect', 84: 'no_connect', 85: 'no_connect', 86: 'passive', 87: 'bidirectional',
            88: 'bidirectional', 89: 'power_in', 90: 'bidirectional', 91: 'bidirectional', 92:
            'passive', 93: 'bidirectional', 94: 'bidirectional', 95: 'bidirectional', 96:
            'bidirectional', 97: 'bidirectional', 98: 'bidirectional', 99: 'bidirectional', 100:
            'passive', 101: 'bidirectional', 102: 'bidirectional', 103: 'passive', 104:
            'bidirectional', 105: 'bidirectional', 106: 'bidirectional', 107: 'bidirectional', 108:
            'power_in', 109: 'power_in', 110: 'no_connect', 111: 'passive', 112: 'bidirectional',
            113: 'bidirectional', 114: 'bidirectional', 115: 'bidirectional', 116: 'bidirectional',
            117: 'bidirectional', 118: 'bidirectional', 119: 'bidirectional', 120: 'bidirectional',
            121: 'bidirectional', 122: 'bidirectional', 123: 'power_in', 124: 'no_connect', 125:
            'no_connect', 126: 'no_connect', 127: 'no_connect', 128: 'bidirectional', 129:
            'bidirectional', 130: 'no_connect', 131: 'no_connect', 132: 'passive', 133: 'passive',
            134: 'bidirectional', 135: 'bidirectional', 136: 'bidirectional', 137: 'bidirectional',
            138: 'bidirectional', 139: 'bidirectional', 140: 'passive', 141: 'bidirectional', 142:
            'bidirectional', 143: 'bidirectional', 144: 'bidirectional'},
    },
    "iCE40HX4K-TQ144": {
        "io": [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28,
            29, 31, 32, 33, 34, 37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 52, 55, 56, 60, 61, 62,
            63, 64, 67, 68, 70, 71, 73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 87, 88, 90, 91,
            93, 94, 95, 96, 97, 98, 99, 101, 102, 104, 105, 106, 107, 110, 112, 113, 114, 115, 116,
            117, 118, 119, 120, 121, 122, 124, 125, 128, 129, 130, 134, 135, 136, 137, 138, 139,
            141, 142, 143, 144],
        "names": {1: 'IOL_2A', 2: 'IOL_2B', 3: 'IOL_3A', 4: 'IOL_3B', 5: 'GND', 6: 'VCCIO_3', 7:
            'IOL_4A', 8: 'IOL_4B', 9: 'IOL_5A', 10: 'IOL_5B', 11: 'IOL_8A', 12: 'IOL_8B', 13:
            'GND', 14: 'GND', 15: 'IOL_10A', 16: 'IOL_10B', 17: 'IOL_12A', 18: 'IOL_12B', 19:
            'IOL_13A', 20: 'IOL_13B_GBIN7', 21: 'IOL_14A_GBIN6', 22: 'IOL_14B', 23: 'IOL_17A', 24:
            'IOL_17B', 25: 'IOL_18A', 26: 'IOL_18B', 27: 'VCC', 28: 'IOL_23A', 29: 'IOL_23B', 30:
            'VCCIO_3', 31: 'IOL_24A', 32: 'IOL_24B', 33: 'IOL_25A', 34: 'IOL_25B', 35: 'NC', 36:
            'NC', 37: 'IOB_56', 38: 'IOB_57', 39: 'IOB_61', 40: 'VCC', 41: 'IOB_63', 42: 'IOB_64',
            43: 'IOB_71', 44: 'IOB_72', 45: 'IOB_73', 46: 'VCCIO_2', 47: 'IOB_79', 48: 'IOB_80',
            49: 'IOB_81_GBIN5', 50: 'NC', 51: 'NC', 52: 'IOB_82_GBIN4', 53: 'GNDPLL0', 54:
            'VCCPLL0', 55: 'IOB_91', 56: 'IOB_94', 57: 'VCCIO_2', 58: 'NC', 59: 'GND', 60:
            'IOB_95', 61: 'IOB_96', 62: 'IOB_102', 63: 'IOB_103_CBSEL0', 64: 'IOB_104_CBSEL1', 65:
            'CDONE', 66: '~{CRESET}', 67: 'IOB_105_SDO', 68: 'IOB_106_SDI', 69: 'GND', 70:
            'IOB_107_SCK', 71: 'IOB_108_SS', 72: 'VCC_SPI', 73: 'IOR_109', 74: 'IOR_110', 75:
            'IOR_111', 76: 'IOR_112', 77: 'NC', 78: 'IOR_114', 79: 'IOR_115', 80: 'IOR_116', 81:
            'IOR_117', 82: 'IOR_118', 83: 'IOR_119', 84: 'IOR_120', 85: 'IOR_128', 86: 'GND', 87:
            'IOR_136', 88: 'IOR_137', 89: 'VCCIO_1', 90: 'IOR_138', 91: 'IOR_139', 92: 'VCC', 93:
            'IOR_140_GBIN3', 94: 'IOR_141_GBIN2', 95: 'IOR_144', 96: 'IOR_146', 97: 'IOR_147', 98:
            'IOR_148', 99: 'IOR_152', 100: 'VCCIO_1', 101: 'IOR_160', 102: 'IOR_161', 103: 'GND',
            104: 'IOR_164', 105: 'IOR_165', 106: 'IOR_166', 107: 'IOR_167', 108: 'VPP_2V5', 109:
            'VPP_FAST', 110: 'IOT_168', 111: 'VCC', 112: 'IOT_169', 113: 'IOT_170', 114: 'IOT_171',
            115: 'IOT_172', 116: 'IOT_173', 117: 'IOT_174', 118: 'IOT_177', 119: 'IOT_178', 120:
            'IOT_179', 121: 'IOT_181', 122: 'IOT_190', 123: 'VCCIO_0', 124: 'IOT_191', 125:
            'IOT_192', 126: 'VCCPLL1', 127: 'GNDPLL1', 128: 'IOT_197_GBIN1', 129: 'IOT_198_GBIN0',
            130: 'IOT_206', 131: 'VCCIO_0', 132: 'GND', 133: 'NC', 134: 'IOT_212', 135: 'IOT_213',
            136: 'IOT_214', 137: 'IOT_215', 138: 'IOT_216', 139: 'IOT_217', 140: 'GND', 141:
            'IOT_219', 142: 'IOT_220', 143: 'IOT_221', 144: 'IOT_222'},
        "types": {1: 'bidirectional', 2: 'bidirectional', 3: 'bidirectional', 4: 'bidirectional',
            5: 'power_in', 6: 'power_in', 7: 'bidirectional', 8: 'bidirectional', 9:
            'bidirectional', 10: 'bidirectional', 11: 'bidirectional', 12: 'bidirectional', 13:
            'passive', 14: 'passive', 15: 'bidirectional', 16: 'bidirectional', 17:
            'bidirectional', 18: 'bidirectional', 19: 'bidirectional', 20: 'bidirectional', 21:
            'bidirectional', 22: 'bidirectional', 23: 'bidirectional', 24: 'bidirectional', 25:
            'bidirectional', 26: 'bidirectional', 27: 'power_in', 28: 'bidirectional', 29:
            'bidirectional', 30: 'passive', 31: 'bidirectional', 32: 'bidirectional', 33:
            'bidirectional', 34: 'bidirectional', 35: 'no_connect', 36: 'no_connect', 37:
            'bidirectional', 38: 'bidirectional', 39: 'bidirectional', 40: 'passive', 41:
            'bidirectional', 42: 'bidirectional', 43: 'bidirectional', 44: 'bidirectional', 45:
            'bidirectional', 46: 'power_in', 47: 'bidirectional', 48: 'bidirectional', 49:
            'bidirectional', 50: 'no_connect', 51: 'no_connect', 52: 'bidirectional', 53:
            'power_in', 54: 'power_in', 55: 'bidirectional', 56: 'bidirectional', 57: 'passive',
            58: 'no_connect', 59: 'passive', 60: 'bidirectional', 61: 'bidirectional', 62:
            'bidirectional', 63: 'bidirectional', 64: 'bidirectional', 65: 'open_collector', 66:
            'input', 67: 'bidirectional', 68: 'bidirectional', 69: 'passive', 70: 'bidirectional',
            71: 'bidirectional', 72: 'power_in', 73: 'bidirectional', 74: 'bidirectional', 75:
            'bidirectional', 76: 'bidirectional', 77: 'no_connect', 78: 'bidirectional', 79:
            'bidirectional', 80: 'bidirectional', 81: 'bidirectional', 82: 'bidirectional', 83:
            'bidirectional', 84: 'bidirectional', 85: 'bidirectional', 86: 'passive', 87:
            'bidirectional', 88: 'bidirectional', 89: 'power_in', 90: 'bidirectional', 91:
            'bidirectional', 92: 'passive', 93: 'bidirectional', 94: 'bidirectional', 95:
            'bidirectional', 96: 'bidirectional', 97: 'bidirectional', 98: 'bidirectional', 99:
            'bidirectional', 100: 'passive', 101: 'bidirectional', 102: 'bidirectional', 103:
            'passive', 104: 'bidirectional', 105: 'bidirectional', 106: 'bidirectional', 107:
            'bidirectional', 108: 'power_in', 109: 'power_in', 110: 'bidirectional', 111:
            'passive', 112: 'bidirectional', 113: 'bidirectional', 114: 'bidirectional', 115:
            'bidirectional', 116: 'bidirectional', 117: 'bidirectional', 118: 'bidirectional', 119:
            'bidirectional', 120: 'bidirectional', 121: 'bidirectional', 122: 'bidirectional', 123:
            'power_in', 124: 'bidirectional', 125: 'bidirectional', 126: 'power_in', 127:
            'power_in', 128: 'bidirectional', 129: 'bidirectional', 130: 'bidirectional', 131:
            'passive', 132: 'passive', 133: 'no_connect', 134: 'bidirectional', 135:
            'bidirectional', 136: 'bidirectional', 137: 'bidirectional', 138: 'bidirectional', 139:
            'bidirectional', 140: 'passive', 141: 'bidirectional', 142: 'bidirectional', 143:
            'bidirectional', 144: 'bidirectional'},
    },
    "iCE40UP5K-SG48": {
        "io": [2, 3, 4, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23, 25, 26, 27, 28,
            31, 32, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48],
        "names": {1: 'VCCIO_2', 2: 'IOB_6a', 3: 'IOB_9b', 4: 'IOB_8a', 5: 'VCC', 6: 'IOB_13b', 7:
            'CDONE', 8: '~{CRESET}', 9: 'IOB_16a', 10: 'IOB_18a', 11: 'IOB_20a', 12: 'IOB_22a', 13:
            'IOB_24a', 14: 'IOB_32a_SPI_SO', 15: 'IOB_34a_SPI_SCK', 16: 'IOB_35b_SPI_SS', 17:
            'IOB_33b_SPI_SI', 18: 'IOB_31b', 19: 'IOB_29b', 20: 'IOB_25b_G3', 21: 'IOB_23b', 22:
            'SPI_VCCIO1', 23: 'IOT_37a', 24: 'VPP_2V5', 25: 'IOT_36b', 26: 'IOT_39a', 27:
            'IOT_38b', 28: 'IOT_41a', 29: 'VCCPLL', 30: 'VCC', 31: 'IOT_42b', 32: 'IOT_43a', 33:
            'VCCIO_0', 34: 'IOT_44b', 35: 'IOT_46b_G0', 36: 'IOT_48b', 37: 'IOT_45a_G1', 38:
            'IOT_50b', 39: 'RGB0', 40: 'RGB1', 41: 'RGB2', 42: 'IOT_51a', 43: 'IOT_49a', 44:
            'IOB_3b_G6', 45: 'IOB_5b', 46: 'IOB_0a', 47: 'IOB_2a', 48: 'IOB_4a'},
        "types": {1: 'power_in', 2: 'bidirectional', 3: 'bidirectional', 4: 'bidirectional', 5:
            'power_in', 6: 'bidirectional', 7: 'open_collector', 8: 'input', 9: 'bidirectional',
            10: 'bidirectional', 11: 'bidirectional', 12: 'bidirectional', 13: 'bidirectional', 14:
            'bidirectional', 15: 'bidirectional', 16: 'bidirectional', 17: 'bidirectional', 18:
            'bidirectional', 19: 'bidirectional', 20: 'bidirectional', 21: 'bidirectional', 22:
            'power_in', 23: 'bidirectional', 24: 'power_in', 25: 'bidirectional', 26:
            'bidirectional', 27: 'bidirectional', 28: 'bidirectional', 29: 'power_out', 30:
            'passive', 31: 'bidirectional', 32: 'bidirectional', 33: 'power_in', 34:
            'bidirectional', 35: 'bidirectional', 36: 'bidirectional', 37: 'bidirectional', 38:
            'bidirectional', 39: 'open_collector', 40: 'open_collector', 41: 'open_collector', 42:
            'bidirectional', 43: 'bidirectional', 44: 'bidirectional', 45: 'bidirectional', 46:
            'bidirectional', 47: 'bidirectional', 48: 'bidirectional'},
    },
}

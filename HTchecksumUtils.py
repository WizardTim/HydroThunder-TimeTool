#!/usr/bin/python3

# This script contains the fuctions called in other HTchecksum scripts.

import sys
import os
import struct
import datetime
import math

DEBUG = False

class HTChecksumUtils:
	version = 0.2

class cmos:
	base_offsets 		= [0x75BE663, 0x75EE663]									# Offset of the first bit of each CMOS block
	
	class header:
		expected_bytes	= bytearray(b'\x01\x00\x00\x00\x98\xba\xdc\xfe')			# Header byte pattern found at the start of each CMOS block
	class area:																		# Area refering to the space that is used in the checksum
		rel_offset		= 0x14														# First bit of the area relative to base_offset
		length 			= 0x1500													# Length of the area checksumed in bytes
	class checksum:
		algorithm		= 'SUM32'													# Checksum algorithm used
		endian			= 'little'													# Endian that determines how bytes are summed
		rel_offset 		= 0xC														# First bit of the checksum  relative to base_offset
		seed 			= 0xFEDCBAF2 # Result of of -0x0123456b						# Seed of the checksum algorithm (this is just the sum of the static header, including it as a seed means we don't have to overwrite the checksum to recalculate it)
	class parity:
		seed 			= False														# Start condition of the parity check state after the header but excluding the checksum
	

def verifyImageHeaders(image_path_list, cmos_img_offset = cmos.base_offsets[0]):
	"""Verifies the offset supplied points to the first bytes of the CMOS block and compares the 'header' bytes
	"""
	for this_file in range(len(image_path_list)):
		with open(image_path_list[this_file], "rb") as f:
			# Seek to first byte, next DWORD is (01 00 00 00)
			f.seek(cmos_img_offset)
			cmos_header = f.read(8)
			
		if (cmos_header == cmos.header.expected_bytes):
			print("  Image #{:2d} PASS : Found [{}] @ {} [{:s}]".format(this_file, cmos_header.hex(' '), hex(cmos_img_offset), image_path_list[this_file]))
			
		else:
			sys.exit("  Image #{:2d} FAIL! : Expected [{}] but found [{}] @ {} [{:s}]".format(this_file, cmos.header.expected_bytes.hex(' '), cmos_header.hex(' '), hex(cmos_img_offset), image_path_list[this_file]))
			
def readChecksum(image_path, checksum_offset = (cmos.base_offsets[0] + cmos.checksum.rel_offset), checksum_algorithm = cmos.checksum.algorithm):
	"""Reads the checksum bytes in an image file for a given offset and checksum algorithm, defaults to first block SUM32
	"""

	match checksum_algorithm:
		case 'SUM8':
			checksum_byte_width = 1
		case 'SUM16':
			checksum_byte_width = 2
		case 'SUM24':
			checksum_byte_width = 3
		case 'SUM32':
			checksum_byte_width = 4
		case _:
			sys.exit("Unknown checksum algorithm '{}'".format(checksum_algorithm))

	with open(image_path, "rb") as f:					
		f.seek(checksum_offset)
		checksum_bytes = f.read(checksum_byte_width)

	return checksum_bytes

def writeChecksum(image_path, checksum_bytes, checksum_offset = (cmos.base_offsets[0] + cmos.checksum.rel_offset)):
	"""Write the checksum bytes to an image file for a given offset, defaults to first block
	"""

	with open(image_path, "r+b") as f:					
		f.seek(checksum_offset)
		f.write(checksum_bytes)


def calculateChecksum(image_path, checksum_start_offset = (cmos.base_offsets[0] + cmos.area.rel_offset), checksum_length_bytes = cmos.area.length, checksum_algorithm = cmos.checksum.algorithm, checksum_endian = cmos.checksum.endian, checksum_seed = cmos.checksum.seed):
	"""Calculates a SUM checksum of a block of continuous bytes in an image file
	"""

	match checksum_algorithm:
		case 'SUM8':
			checksum_byte_width = 1
			checksum_mask = 0xFF
			checksum_length_reads = checksum_length_bytes
		case 'SUM16':
			checksum_byte_width = 2
			checksum_mask = 0xFFFF
			checksum_length_reads = checksum_length_bytes / checksum_byte_width
			if checksum_length_reads != int(checksum_length_reads):
				sys.exit("Checksum data length mismatch with algorithm, length must be multiple of checksum byte width '{}'".format(checksum_byte_width))
		case 'SUM24':
			checksum_byte_width = 3
			checksum_mask = 0xFFFFFF
			checksum_length_reads = checksum_length_bytes / checksum_byte_width
			if checksum_length_reads != int(checksum_length_reads):
				sys.exit("Checksum data length mismatch with algorithm, length must be multiple of checksum byte width '{}'".format(checksum_byte_width))
		case 'SUM32':
			checksum_byte_width = 4
			checksum_mask = 0xFFFFFFFF
			checksum_length_reads = checksum_length_bytes / checksum_byte_width
			if checksum_length_reads != int(checksum_length_reads):
				sys.exit("Checksum data length mismatch with algorithm, length must be multiple of checksum byte width '{}'".format(checksum_byte_width))
		case _:
			sys.exit("Unknown checksum algorithm {}".format(checksum_algorithm))
			
	checksum_seed = checksum_seed % checksum_mask
	checksum_length_reads = int(checksum_length_reads)
	parity_bit = cmos.parity.seed
			
	with open(image_path, "rb") as f_s:						
		f_s.seek(checksum_start_offset)
		
		checksum_sum = checksum_seed
		num_sums = 0
		for this_data_offset in range(checksum_length_reads):
			this_byte = f_s.read(checksum_byte_width)
			num_sums += 1
			
			this_byte_int = int.from_bytes(this_byte, checksum_endian, signed=False)
			checksum_sum = (this_byte_int + checksum_sum)						
			
			# Calculate parity of each byte
			if this_byte_int % 2 == 0:
				parity_bit = not(parity_bit)
		
		# Simulate overflow behaviour of uint32
		overflows = math.floor(checksum_sum / 0xFFFFFFFF)
		checksum_sum = checksum_sum - (overflows)
		
		# Extract lower bytes for checksum width
		checksum_sum = checksum_sum % checksum_mask		
		checksum_sum_bytes = checksum_sum.to_bytes(checksum_byte_width,checksum_endian, signed=False)
		
		checksum_end_offset = f_s.tell() - 1
			
	if DEBUG:
		print("\n" + checksum_algorithm + " | 0x" + checksum_start_offset.to_bytes(4,checksum_endian).hex() + " → 0x" + (checksum_end_offset).to_bytes(4,checksum_endian).hex() + " |  " + "{:10d}".format(num_sums) + " |  " + this_byte.hex(' ') + "  | " + checksum_sum_bytes.hex(' ') + " | ")
			
	last_byte = this_byte
	
	# Add the parity of the checksum as well
	if checksum_sum % 2 == 0:
		parity_bit = not(parity_bit)
	
	# Replace the last bit of the checksum with the parity bit
	checksum_sum = checksum_sum % (checksum_mask - 1)
	checksum_sum += parity_bit
	checksum_sum_bytes = checksum_sum.to_bytes(checksum_byte_width,checksum_endian, signed=False)
			
	return checksum_sum_bytes, checksum_start_offset, checksum_end_offset, num_sums, last_byte


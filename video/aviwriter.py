from struct import pack, unpack
from ctypes import BigEndianStructure, c_uint
from io import SEEK_CUR

from video import CODEC, VideoWriter

class H263FrameHeader(BigEndianStructure):
    _fields_ = [
                  ('header',                c_uint, 17),
                  ('picformat',             c_uint, 5),
                  ('ts',                    c_uint, 8),
                  ('format',                c_uint, 3)
                ]

class VP6FrameHeader(BigEndianStructure):
    _fields_ = [
                  ('deltaFrameFlag',        c_uint, 1),
                  ('quant',                 c_uint, 6),
                  ('separatedCoeffFlag',    c_uint, 1),
                  ('subVersion',            c_uint, 5),
                  ('filterHeader',          c_uint, 2),
                  ('interlacedFlag',        c_uint, 1)
                  ]


class AVIWriter(VideoWriter):
    __slots__  = [ '_fd', '_path', '_codecID', '_warnings', '_isAlphaWriter', '_alphaWriter' ]
    __slots__ += [ '_width', '_height', '_frameCount' ]
    __slots__ += [ '_index', '_moviDataSize' ]

    # Chunk:          Off:  Len:
    #
    # RIFF AVI          0    12
    #   LIST hdrl      12    12
    #     avih         24    64
    #     LIST strl    88    12
    #       strh      100    64
    #       strf      164    48
    #   LIST movi     212    12
    #     (frames)    224   ???
    #   idx1          ???   ???

    def WriteFourCC(self, fourCC):
        if len(fourCC) != 4:
            raise Exception('Invalid fourCC length')
        self._fd.write(fourCC)

    def CodecFourCC(self):
        if self._codecID == CODEC.H263:
            return 'FLV1'
        elif self._codecID in (CODEC.VP6, CODEC.VP6v2):
            return 'VP6F'

    def __init__(self, path, codecID, warnings, isAlphaWriter=False):
        self._path = path
        self._codecID = codecID
        self._isAlphaWriter = isAlphaWriter
        self._alphaWriter = None
        self._warnings = warnings

        self._width = self._height = self._frameCount = 0
        self._index = []
        self._moviDataSize = 0

        if codecID not in (CODEC.H263, CODEC.VP6, CODEC.VP6v2):
            raise Exception('Unsupported video codec')

        self._fd = open(path, 'wb')

        if (codecID == CODEC.VP6v2) and not isAlphaWriter:
            self._alphaWriter = AVIWriter(path[:-4] + 'alpha.avi', codecID, warnings, True)

        self.WriteFourCC('RIFF')
        self._fd.write(pack('<I', 0)) # chunk size
        self.WriteFourCC('AVI ')

        self.WriteFourCC('LIST')
        self._fd.write(pack('<I', 192))
        self.WriteFourCC('hdrl')

        self.WriteFourCC('avih')
        self._fd.write(pack('<I', 56))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0x10))
        self._fd.write(pack('<I', 0)) # frame count
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 1))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0)) # width
        self._fd.write(pack('<I', 0)) # height
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))

        self.WriteFourCC('LIST')
        self._fd.write(pack('<I', 116))
        self.WriteFourCC('strl')

        self.WriteFourCC('strh')
        self._fd.write(pack('<I', 56))
        self.WriteFourCC('vids')
        self.WriteFourCC(self.CodecFourCC())
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0)) # frame rate denominator
        self._fd.write(pack('<I', 0)) # frame rate numerator
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0)) # frame count
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<i', -1))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<H', 0))
        self._fd.write(pack('<H', 0))
        self._fd.write(pack('<H', 0)) # width
        self._fd.write(pack('<H', 0)) # height

        self.WriteFourCC('strf')
        self._fd.write(pack('<I', 40))
        self._fd.write(pack('<I', 40))
        self._fd.write(pack('<I', 0)) # width
        self._fd.write(pack('<I', 0)) # height
        self._fd.write(pack('<H', 1))
        self._fd.write(pack('<H', 24))
    
        self.WriteFourCC(self.CodecFourCC())
        self._fd.write(pack('<I', 0)) # biSizeImage
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
        self._fd.write(pack('<I', 0))
    
        self.WriteFourCC('LIST')
        self._fd.write(pack('<I', 0)) # chunk size
        self.WriteFourCC('movi')

    def WriteChunk(self, chunk, timeStamp, frameType):
        offset = 0
        length = len(chunk)

        if self._codecID == 4:
            offset = 1
            length -= 1
        elif self._codecID == 5:
            offset = 4
            if length >= 4:
                alphaOffset = unpack('>I', chunk[:4])[0] & 0xffffff
                if not self._isAlphaWriter:
                    length = alphaOffset
                else:
                    offset += alphaOffset
                    length -= offset
            else:
                length = 0

        length = max(length, 0)
        length = min(length, len(chunk) - offset)

        self._index.append(0x10 if (frameType == 1) else 0)
        self._index.append(self._moviDataSize + 4)
        self._index.append(length)

        if (self._width == 0) and (self._height == 0):
            self.GetFrameSize(chunk)

        self.WriteFourCC('00dc')
        self._fd.write(pack('<i', length))
        self._fd.write(chunk[offset:offset + length])

        if (length % 2) != 0:
            self._fd.write('\x00')
            length += 1

        self._moviDataSize += length + 8
        self._frameCount += 1

        if self._alphaWriter is not None:
            self._alphaWriter.WriteChunk(chunk, timeStamp, frameType)

    def GetFrameSize(self, chunk):
        if self._codecID == CODEC.H263:
            # Reference: flv_h263_decode_picture_header from libavcodec's h263.c
            if len(chunk) < 10: return

            hdr = H263FrameHeader.from_buffer_copy(chunk)

            if hdr.header != 1: # h263 header
                return

            if hdr.picformat not in (0, 1): # picture format 0: h263 escape codes 1: 11-bit escape codes 
                return

            # TODO: h263 frame header
        
        elif self._codecID in (CODEC.VP6, CODEC.VP6v2):
            # Reference: vp6_parse_header from libavcodec's vp6.c
            skip = 1 if (self._codecID == CODEC.VP6) else 4
            if len(chunk) < (skip + 8): return

            hdr = VP6FrameHeader.from_buffer_copy(chunk, skip)

            if hdr.deltaFrameFlag != 0:
                return

            if hdr.separatedCoeffFlag or hdr.filterHeader: # skip 16 bit
                xy = chunk[skip + 2:skip + 4]
            else:
                xy = chunk[skip:skip + 2]

            self._height = ord(xy[0]) * 16
            self._width = ord(xy[1]) * 16

            # chunk[0] contains the width and height (4 bits each, respectively) that should
            # be cropped off during playback, which will be non-zero if the encoder padded
            # the frames to a macroblock boundary.  But if you use this adjusted size in the
            # AVI header, DirectShow seems to ignore it, and it can cause stride or chroma
            # alignment problems with VFW if the width/height aren't multiples of 4.
            if not self._isAlphaWriter:
                cropX = ord(chunk[0]) >> 4
                cropY = ord(chunk[0]) & 0xf
                if (cropX != 0) or (cropY != 0):
                    self._warnings.append('Suggested cropping: %d pixels from right, %d pixels from bottom' % (cropX, cropY))

    __slots__ += [ '_indexChunkSize' ]
    def WriteIndexChunk(self):
        indexDataSize = self._frameCount * 16

        self.WriteFourCC('idx1')
        self._fd.write(pack('<I', indexDataSize))

        for i in xrange(self._frameCount):
            self.WriteFourCC('00dc')
            self._fd.write(pack('<I', self._index[(i * 3) + 0]))
            self._fd.write(pack('<I', self._index[(i * 3) + 1]))
            self._fd.write(pack('<I', self._index[(i * 3) + 2]))

        self._indexChunkSize = indexDataSize + 8

    def Finish(self, averageFrameRate):
        self.WriteIndexChunk()

        self._fd.seek(4)
        self._fd.write(pack('<I', 224 + self._moviDataSize + self._indexChunkSize - 8))

        self._fd.seek(24 + 8)
        self._fd.write(pack('<I', 0))
        self._fd.seek(12, SEEK_CUR)
        self._fd.write(pack('<I', self._frameCount))
        self._fd.seek(12, SEEK_CUR)
        self._fd.write(pack('<I', self._width))
        self._fd.write(pack('<I', self._height))

        self._fd.seek(100 + 28)
        self._fd.write(pack('<I', averageFrameRate.denominator))
        self._fd.write(pack('<I', averageFrameRate.numerator))
        self._fd.seek(4, SEEK_CUR)
        self._fd.write(pack('<I', self._frameCount))
        self._fd.seek(16, SEEK_CUR)
        self._fd.write(pack('<H', self._width))
        self._fd.write(pack('<H', self._height))

        self._fd.seek(164 + 12)
        self._fd.write(pack('<I', self._width))
        self._fd.write(pack('<I', self._height))
        self._fd.seek(8, SEEK_CUR)
        self._fd.write(pack('<I', self._width * self._height * 6))

        self._fd.seek(212 + 4)
        self._fd.write(pack('<I', self._moviDataSize + 4))

        self._fd.close()

        if self._alphaWriter is not None:
            self._alphaWriter.Finish(averageFrameRate)
            self._alphaWriter = None
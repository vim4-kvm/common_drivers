// SPDX-License-Identifier: GPL-2.0+
/* Exclusive hardware test: repeat close/STREAMOFF/REQBUFS(0) with a live
 * exported fd and unread DONE buffers. After exit the module must unload.
 * Build: cc -O2 -Wall -Wextra test_lifecycle.c -o test_lifecycle
 * Usage: test_lifecycle /dev/video_cap [cycles]
 */
#include <fcntl.h>
#include <linux/dma-buf.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct dmabuf_req { uint32_t index; int32_t fd; uint32_t size, reserved; };
#define GET_DMABUF _IOWR('V', 192, struct dmabuf_req)

static void check(int result, const char *operation)
{
	if (result < 0) {
		perror(operation);
		exit(1);
	}
}

int main(int argc, char **argv)
{
	if (argc < 2 || argc > 3)
		return 2;
	int cycles = argc == 3 ? atoi(argv[2]) : 30;
	if (cycles <= 0)
		return 2;
	for (int cycle = 0; cycle < cycles; cycle++) {
		int fd = open(argv[1], O_RDWR | O_NONBLOCK);
		check(fd, "open");
		enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
		struct v4l2_requestbuffers req = {
			.count = 4, .type = type, .memory = V4L2_MEMORY_MMAP,
		};
		check(ioctl(fd, VIDIOC_REQBUFS, &req), "REQBUFS");
		for (unsigned i = 0; i < req.count; i++) {
			struct v4l2_plane plane = {0};
			struct v4l2_buffer buf = {
				.type = type, .memory = V4L2_MEMORY_MMAP,
				.index = i, .length = 1, .m.planes = &plane,
			};
			check(ioctl(fd, VIDIOC_QBUF, &buf), "QBUF");
		}
		check(ioctl(fd, VIDIOC_STREAMON, &type), "STREAMON");
		struct dmabuf_req exported = { .fd = -1 };
		/* Leave the final token DONE and the others dequeued, never requeue.
		 * buf_cleanup must release both kinds of token-owned references. */
		for (unsigned i = 0; i < req.count; i++) {
			struct pollfd pfd = { .fd = fd, .events = POLLIN };
			int ready = poll(&pfd, 1, 3000);
			if (ready <= 0) {
				fprintf(stderr, "capture timeout/error: %d\n", ready);
				return 1;
			}
			if (i + 1 == req.count)
				break;
			struct v4l2_plane plane = {0};
			struct v4l2_buffer buf = {
				.type = type, .memory = V4L2_MEMORY_MMAP,
				.length = 1, .m.planes = &plane,
			};
			check(ioctl(fd, VIDIOC_DQBUF, &buf), "DQBUF");
			if (i == 0) {
				exported.index = buf.index;
				check(ioctl(fd, GET_DMABUF, &exported), "GET_DMABUF");
			}
		}
		if (cycle % 3 != 0)
			check(ioctl(fd, VIDIOC_STREAMOFF, &type), "STREAMOFF");
		if (cycle % 3 == 2) {
			req.count = 0;
			check(ioctl(fd, VIDIOC_REQBUFS, &req), "REQBUFS zero");
		}
		check(close(fd), "close device");
		/* Queue teardown must not revoke a separately owned DMA-BUF. */
		void *data = mmap(NULL, exported.size, PROT_READ, MAP_SHARED, exported.fd, 0);
		if (data == MAP_FAILED) {
			perror("mmap exported fd after close");
			return 1;
		}
		struct dma_buf_sync sync = { .flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ };
		check(ioctl(exported.fd, DMA_BUF_IOCTL_SYNC, &sync), "SYNC START");
		volatile uint8_t sample = *(uint8_t *)data;
		(void)sample;
		/* Cached capture mappings must stay read-only, even via private
		 * mappings or a later mprotect, because consumers share the frame. */
		void *writable = mmap(NULL, 4096, PROT_READ | PROT_WRITE,
			MAP_PRIVATE, exported.fd, 0);
		if (writable != MAP_FAILED ||
		    mprotect(data, 4096, PROT_READ | PROT_WRITE) == 0) {
			fprintf(stderr, "capture mapping unexpectedly writable\n");
			return 1;
		}
		/* A page-sized submapping must honor its nonzero file offset. */
		void *partial = mmap(NULL, 4096, PROT_READ, MAP_SHARED, exported.fd, 4096);
		if (partial == MAP_FAILED) {
			perror("partial mmap");
			return 1;
		}
		for (unsigned i = 0; i < 4096; i++) {
			if (((uint8_t *)partial)[i] != ((uint8_t *)data)[4096 + i]) {
				fprintf(stderr, "partial mapping offset mismatch\n");
				return 1;
			}
		}
		check(munmap(partial, 4096), "munmap partial");
		sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
		check(ioctl(exported.fd, DMA_BUF_IOCTL_SYNC, &sync), "SYNC END");
		check(munmap(data, exported.size), "munmap");
		check(close(exported.fd), "close DMA-BUF");
	}
	printf("PASS: %d close/streamoff/reqbufs cycles\n", cycles);
	return 0;
}

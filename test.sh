#!/usr/bin/env bash
CUDA_VISIBLE_DEVICES=0 python main.py \
    --output_dir ./zssr/ \
    --summary_dir ./zssr/log/ \
    --mode inference \
    --is_training False \
    --task SRGAN \
    --input_dir_LR /media/wit/cc/ZSSR/ \
    --pre_trained_model True \
    --checkpoint ./ckpt/model-200000

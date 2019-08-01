#!/usr/bin/env bash
CUDA_VISIBLE_DEVICES=3 python main.py \
    --output_dir ./ck/ \
    --summary_dir ./ck/log/ \
    --mode train \
    --is_training True \
    --task SRGAN \
    --batch_size 16 \
    --flip True \
    --random_crop True \
    --crop_size 24 \
    --input_dir_LR /home/witai/cc/data/LFW/lr/ \
    --input_dir_HR /home/witai/cc/data/LFW/hr/ \
    --ratio 0.01 \
    --p_ratio 0.02 \
    --learning_rate 0.0001 \
    --decay_step 100000 \
    --decay_rate 0.1 \
    --stair True \
    --beta 0.9 \
    --max_iter 200000


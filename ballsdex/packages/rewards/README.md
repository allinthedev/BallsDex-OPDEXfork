# This package provides a reward distribution system for a Discord bot.

## Features
- Administrators can batch distribute rewards to selected users based on economy type, regime type, rarity, and other criteria.
- Users can claim pending rewards via button.

## How to Distribute Rewards
- Administrators can use the `/rewards distribute` command to send rewards.
- You can specify criteria such as economy type, regime type, rarity range, number of rewards, and target users or roles.
> **Warning:** The `role` argument requires the **Server Members Intent** to be enabled in your Discord Developer Portal. Without this privileged intent, the bot may not be able to fetch members with the specified role.

## User Experience
- When a reward is distributed, users will receive a private message notification (if possible) informing them about the reward type and details.
- Users can click the button below to view and claim their pending rewards.
- After claiming, users will receive a confirmation message showing the reward they received.
